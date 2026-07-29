from sqlalchemy.dialects import mysql

from app.modules.policies.service import PolicyQueryService


class RecordingSession:
    def __init__(self) -> None:
        self.scalar_statements = []
        self.scalars_statements = []

    def scalar(self, statement):
        self.scalar_statements.append(statement)
        return 0

    def scalars(self, statement):
        self.scalars_statements.append(statement)
        return []


def test_policy_id_page_query_is_valid_for_mysql_distinct_ordering() -> None:
    session = RecordingSession()

    result = PolicyQueryService(session).list_policies(source_id=7)

    assert result.items == []
    statement = session.scalars_statements[0]
    sql = str(statement.compile(dialect=mysql.dialect())).upper()
    assert "DISTINCT" not in sql
    assert "EXISTS" in sql
    assert "ORDER BY" in sql
