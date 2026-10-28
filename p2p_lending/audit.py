"""Audit trail helper - every important status change is written to audit_logs."""


def log(conn, entity_type, entity_id, action, old_value=None, new_value=None, actor="system", details=None):
    """Insert one audit row. The caller is responsible for conn.commit().
    The audit_logs table (Week 1) has old_value / new_value columns, so any extra
    explanation (`details`) is stored after the new value, e.g. 'active | principal 5,000'.
    """
    if details:
        new_value = f"{new_value} | {details}" if new_value is not None else details
    conn.execute(
        "INSERT INTO audit_logs(entity_type, entity_id, action, old_value, new_value, actor)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (entity_type, entity_id, action,
         None if old_value is None else str(old_value),
         None if new_value is None else str(new_value), actor),
    )
