GERENCIAL_SCHEMA = "gerencial"

PERMISSION_LABELS = {
    "monitoramento_read": "Ver monitoramento",
    "monitoramento_write": "Editar producao gerencial",
    "parecer_read": "Ver pareceres",
    "parecer_write": "Solicitar/atualizar pareceres",
    "protocolo_read": "Ver protocolos",
    "protocolo_write": "Criar/editar protocolos",
    "colchao_read": "Ver colchao",
    "colchao_write": "Editar colchao",
    "view_audit": "Ver auditoria",
    "view_schema_versions": "Ver versoes de schema",
    "manage_users": "Criar/editar usuarios",
    "manage_backups": "Criar/listar backups",
    "restore_backup": "Restaurar backup",
    "edit_schema": "Editar carteiras e schemas",
    "approve_parecer": "Aprovar/reprovar parecer",
    "delete_agreements": "Excluir acordos",
}

DEFAULT_ROLE_PERMISSIONS = {
    "superadmin": {permission: True for permission in PERMISSION_LABELS},
    "admin": {permission: True for permission in PERMISSION_LABELS},
    "gerencial": {
        "monitoramento_read": True, "monitoramento_write": True,
        "parecer_read": True, "parecer_write": True,
        "protocolo_read": True, "protocolo_write": True,
        "colchao_read": True, "colchao_write": True,
        "view_audit": True, "view_schema_versions": True,
        "manage_users": False, "manage_backups": False, "restore_backup": False,
        "edit_schema": False, "approve_parecer": True, "delete_agreements": True,
    },
    "supervisor": {
        "monitoramento_read": True, "monitoramento_write": False,
        "parecer_read": True, "parecer_write": False,
        "protocolo_read": True, "protocolo_write": False,
        "colchao_read": True, "colchao_write": False,
        "view_audit": True, "view_schema_versions": True,
        "manage_users": False, "manage_backups": False, "restore_backup": False,
        "edit_schema": False, "approve_parecer": True, "delete_agreements": False,
    },
}
