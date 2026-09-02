from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO
import re
import unicodedata

import pdfplumber


class AlphaMetaPdfError(ValueError):
    pass


def normalize_portfolio_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9]+", "", ascii_value.upper())


def decimal_to_json(value: Decimal) -> str:
    return f"{value:.2f}"


class AlphaMetaPdfParser:
    OFFICE_BAND = (30, 62)
    PORTFOLIO_BAND = (62, 105)
    GROUP_BAND = (105, 132)
    META_CAIXA_BANDS = ((185, 207), (207, 230), (230, 255))
    RETOMADAS_COUNT_BANDS = ((265, 283), (283, 301), (301, 320))
    RETOMADAS_VALUE_BANDS = ((345, 370), (370, 394), (394, 420))
    META_PNT_BANDS = ((435, 466), (466, 493), (493, 520))

    def parse(self, content: bytes, file_name: str = "metas.pdf") -> dict:
        if not content:
            raise AlphaMetaPdfError("O PDF de metas esta vazio.")
        try:
            with pdfplumber.open(BytesIO(content)) as document:
                if len(document.pages) != 1:
                    raise AlphaMetaPdfError("O PDF trimestral da Alpha deve possuir uma pagina.")
                page = document.pages[0]
                text = page.extract_text() or ""
                words = page.extract_words(x_tolerance=2, y_tolerance=2)
        except AlphaMetaPdfError:
            raise
        except Exception as exc:
            raise AlphaMetaPdfError(f"Nao foi possivel ler o PDF: {exc}") from exc

        title_match = re.search(r"PNT\s*-\s*AUTOS\s+([1-4])T(\d{4})", text, re.IGNORECASE)
        if not title_match:
            raise AlphaMetaPdfError("O arquivo nao foi reconhecido como uma meta PNT AUTOS trimestral.")
        quarter_number, year_text = title_match.groups()
        quarter = f"{quarter_number}T{year_text}"
        months = self._extract_months(words, int(year_text), int(quarter_number))
        rows = self._group_rows(words)
        goals = self._extract_goals(rows, months)
        footer = self._extract_footer(rows, months)
        validation = self._validate(goals, footer, months)
        return {
            "file_name": file_name,
            "quarter": quarter,
            "office": "ESCRITORIO_DEMO",
            "months": [month.isoformat() for month in months],
            "goals": goals,
            "totals": footer,
            "validation": validation,
        }

    def _extract_months(self, words: list[dict], year: int, quarter: int) -> list[date]:
        header_months = []
        for word in words:
            if 108 <= float(word["top"]) <= 120 and re.fullmatch(r"\d{6}", word["text"]):
                value = word["text"]
                parsed = date(int(value[:4]), int(value[4:]), 1)
                if parsed not in header_months:
                    header_months.append(parsed)
        expected = [date(year, month, 1) for month in range((quarter - 1) * 3 + 1, quarter * 3 + 1)]
        if header_months[:3] != expected:
            raise AlphaMetaPdfError(
                "As competencias do cabecalho nao correspondem ao trimestre informado."
            )
        return expected

    @staticmethod
    def _group_rows(words: list[dict]) -> list[list[dict]]:
        grouped: list[tuple[float, list[dict]]] = []
        for word in sorted(words, key=lambda item: (float(item["top"]), float(item["x0"]))):
            top = float(word["top"])
            if not 120 <= top <= 455:
                continue
            if grouped and abs(grouped[-1][0] - top) <= 0.75:
                grouped[-1][1].append(word)
            else:
                grouped.append((top, [word]))
        return [sorted(row, key=lambda item: float(item["x0"])) for _, row in grouped]

    def _extract_goals(self, rows: list[list[dict]], months: list[date]) -> list[dict]:
        goals: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for words in rows:
            office = self._text(words, self.OFFICE_BAND)
            portfolio = self._text(words, self.PORTFOLIO_BAND)
            if office != "ESCRITORIO_DEMO" or not portfolio or portfolio.upper().startswith("TOTAL"):
                continue
            group_name = self._text(words, self.GROUP_BAND).replace(" / ", " / ")
            portfolio_key = normalize_portfolio_key(portfolio)
            if not portfolio_key:
                continue
            month_values = []
            for index, competence in enumerate(months):
                meta_caixa = self._number(words, self.META_CAIXA_BANDS[index])
                retomadas_count = int(self._number(words, self.RETOMADAS_COUNT_BANDS[index]))
                retomadas_value = self._number(words, self.RETOMADAS_VALUE_BANDS[index])
                meta_pnt = self._number(words, self.META_PNT_BANDS[index])
                unique_key = (portfolio_key, competence.isoformat())
                if unique_key in seen:
                    raise AlphaMetaPdfError(
                        f"Portfolio duplicado no PDF: {portfolio} em {competence:%m/%Y}."
                    )
                seen.add(unique_key)
                month_values.append({
                    "competence": competence.isoformat(),
                    "meta_caixa": decimal_to_json(meta_caixa),
                    "retomadas_count": retomadas_count,
                    "retomadas_value": decimal_to_json(retomadas_value),
                    "meta_pnt": decimal_to_json(meta_pnt),
                })
            goals.append({
                "portfolio": portfolio,
                "portfolio_key": portfolio_key,
                "group_name": group_name,
                "months": month_values,
            })
        if not goals:
            raise AlphaMetaPdfError("Nenhuma meta de portfolio foi localizada no PDF.")
        return goals

    def _extract_footer(self, rows: list[list[dict]], months: list[date]) -> list[dict]:
        for words in reversed(rows):
            if self._text(words, self.OFFICE_BAND) != "ESCRITORIO_DEMO":
                continue
            if self._text(words, self.PORTFOLIO_BAND).upper().replace(" ", "") != "TOTALGERAL":
                continue
            return [
                {
                    "competence": competence.isoformat(),
                    "meta_caixa": decimal_to_json(self._number(words, self.META_CAIXA_BANDS[index])),
                    "retomadas_count": int(self._number(words, self.RETOMADAS_COUNT_BANDS[index])),
                    "retomadas_value": decimal_to_json(self._number(words, self.RETOMADAS_VALUE_BANDS[index])),
                    "meta_pnt": decimal_to_json(self._number(words, self.META_PNT_BANDS[index])),
                }
                for index, competence in enumerate(months)
            ]
        raise AlphaMetaPdfError("O total geral nao foi localizado no PDF.")

    def _validate(self, goals: list[dict], footer: list[dict], months: list[date]) -> dict:
        errors: list[str] = []
        warnings: list[str] = []
        calculated_totals = []
        for competence in months:
            month_key = competence.isoformat()
            entries = [
                item
                for goal in goals
                for item in goal["months"]
                if item["competence"] == month_key
            ]
            meta_caixa = sum((Decimal(item["meta_caixa"]) for item in entries), Decimal("0"))
            count = sum(int(item["retomadas_count"]) for item in entries)
            retomadas_value = sum((Decimal(item["retomadas_value"]) for item in entries), Decimal("0"))
            meta_pnt = sum((Decimal(item["meta_pnt"]) for item in entries), Decimal("0"))
            for goal in goals:
                entry = next(item for item in goal["months"] if item["competence"] == month_key)
                if Decimal(entry["meta_pnt"]) != Decimal(entry["meta_caixa"]) + Decimal(entry["retomadas_value"]):
                    errors.append(
                        f"{goal['portfolio']} em {competence:%m/%Y}: Meta PNT difere de Caixa + Retomadas."
                    )
            calculated_totals.append({
                "competence": month_key,
                "meta_caixa": decimal_to_json(meta_caixa),
                "retomadas_count": count,
                "retomadas_value": decimal_to_json(retomadas_value),
                "meta_pnt": decimal_to_json(meta_pnt),
            })
            expected = next(item for item in footer if item["competence"] == month_key)
            differences = {
                key: abs(Decimal(str(calculated_totals[-1][key])) - Decimal(str(expected[key])))
                for key in ("meta_caixa", "retomadas_count", "retomadas_value", "meta_pnt")
            }
            if any(value > Decimal("2.00") for value in differences.values()):
                errors.append(
                    f"Total calculado de {competence:%m/%Y} nao confere com o TOTAL GERAL do PDF."
                )
            elif any(value for value in differences.values()):
                warnings.append(
                    f"{competence:%m/%Y}: diferenca de arredondamento de ate "
                    f"{max(differences.values()):.2f} entre portfolios e TOTAL GERAL."
                )
        zero_goals = sum(
            1
            for goal in goals
            if all(Decimal(month["meta_pnt"]) == 0 for month in goal["months"])
        )
        if zero_goals:
            warnings.append(f"{zero_goals} portfolios possuem meta zerada no trimestre.")
        return {
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
            "portfolio_count": len(goals),
            "goal_count": len(goals) * len(months),
            "calculated_totals": calculated_totals,
        }

    @staticmethod
    def _text(words: list[dict], band: tuple[float, float]) -> str:
        values = [
            word["text"].strip()
            for word in words
            if band[0] <= float(word["x0"]) < band[1] and word["text"].strip()
        ]
        return " ".join(values).strip()

    @staticmethod
    def _number(words: list[dict], band: tuple[float, float]) -> Decimal:
        fragments = [
            word["text"].strip()
            for word in words
            if band[0] <= float(word["x0"]) < band[1] and word["text"].strip()
        ]
        raw = "".join(fragments).replace("R$", "").replace(" ", "")
        if not raw or raw == "-":
            return Decimal("0")
        raw = raw.replace(".", "").replace(",", ".")
        try:
            return Decimal(raw)
        except InvalidOperation as exc:
            raise AlphaMetaPdfError(f"Valor numerico invalido no PDF: {raw}") from exc
