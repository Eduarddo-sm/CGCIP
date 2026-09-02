from pathlib import Path
import unittest

from services.alpha_meta_pdf_service import AlphaMetaPdfParser, normalize_portfolio_key


FIXTURE = Path(__file__).parent / "fixtures" / "alpha_meta_3t2026.pdf"


class AlphaMetaPdfParserTestCase(unittest.TestCase):
    def test_normalize_portfolio_key(self):
        self.assertEqual(
            normalize_portfolio_key("Instituicao Financeira XXIV"),
            "INSTITUICAOFINANCEIRAXXIV",
        )

    @unittest.skipUnless(FIXTURE.exists(), "Fixture PDF nao disponivel")
    def test_parse_official_alpha_quarter_pdf(self):
        result = AlphaMetaPdfParser().parse(FIXTURE.read_bytes(), FIXTURE.name)

        self.assertEqual(result["quarter"], "3T2026")
        self.assertEqual(result["months"], ["2026-07-01", "2026-08-01", "2026-09-01"])
        self.assertTrue(result["validation"]["valid"])
        self.assertEqual(result["validation"]["portfolio_count"], 54)
        self.assertEqual(result["totals"], [
            {
                "competence": "2026-07-01",
                "meta_caixa": "422576.00",
                "retomadas_count": 3,
                "retomadas_value": "133000.00",
                "meta_pnt": "555576.00",
            },
            {
                "competence": "2026-08-01",
                "meta_caixa": "376673.00",
                "retomadas_count": 2,
                "retomadas_value": "93000.00",
                "meta_pnt": "469673.00",
            },
            {
                "competence": "2026-09-01",
                "meta_caixa": "376673.00",
                "retomadas_count": 2,
                "retomadas_value": "93000.00",
                "meta_pnt": "469673.00",
            },
        ])
        xxiv = next(
            item
            for item in result["goals"]
            if item["portfolio_key"] == "INSTITUICAOFINANCEIRAXXIV"
        )
        self.assertEqual(xxiv["months"][0]["meta_caixa"], "48726.00")
        self.assertEqual(xxiv["months"][0]["retomadas_value"], "40000.00")
        self.assertEqual(xxiv["months"][0]["meta_pnt"], "88726.00")
