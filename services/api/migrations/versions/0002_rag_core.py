"""RAG core: documents, chunks, pgvector embeddings, with forced tenant RLS.

Every tenant table has:
* workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE
* ENABLE and FORCE row-level security
* Per-command policies restricting access to app_workspace_id()
* Least-privilege grants to supportpilot_app
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "supportpilot_app"

_STATEMENTS_UP = [
    # Vector extension for embeddings (1536 dims, e.g. OpenAI / voyage / custom)
    "CREATE EXTENSION IF NOT EXISTS vector",
    # --- documents table ----------------------------------------------------------------------
    """
    CREATE TABLE documents (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        workspace_id uuid NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
        filename text NOT NULL,
        content_type text NOT NULL,
        size_bytes integer NOT NULL,
        status text NOT NULL DEFAULT 'pending',
        error_message text,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT documents_filename_length CHECK (char_length(filename) BETWEEN 1 AND 255),
        CONSTRAINT documents_content_type_length
            CHECK (char_length(content_type) BETWEEN 1 AND 100),
        CONSTRAINT documents_size_positive CHECK (size_bytes > 0 AND size_bytes <= 10485760),
        CONSTRAINT documents_status_valid
            CHECK (status IN ('pending', 'processing', 'indexed', 'failed'))
    )
    """,
    "CREATE INDEX ix_documents_workspace_id ON documents (workspace_id)",
    "CREATE INDEX ix_documents_workspace_status ON documents (workspace_id, status)",
    # Forced RLS on documents
    "ALTER TABLE documents ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE documents FORCE ROW LEVEL SECURITY",
    """
    CREATE POLICY documents_select ON documents FOR SELECT
        USING (workspace_id = app_workspace_id())
    """,
    """
    CREATE POLICY documents_insert ON documents FOR INSERT
        WITH CHECK (workspace_id = app_workspace_id())
    """,
    """
    CREATE POLICY documents_update ON documents FOR UPDATE
        USING (workspace_id = app_workspace_id())
        WITH CHECK (workspace_id = app_workspace_id())
    """,
    """
    CREATE POLICY documents_delete ON documents FOR DELETE
        USING (workspace_id = app_workspace_id())
    """,
    # --- document_chunks table ----------------------------------------------------------------
    """
    CREATE TABLE document_chunks (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        workspace_id uuid NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
        document_id uuid NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
        chunk_index integer NOT NULL,
        content text NOT NULL,
        token_count integer NOT NULL,
        embedding vector(1536) NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT document_chunks_document_index_uniq UNIQUE (document_id, chunk_index),
        CONSTRAINT document_chunks_index_nonnegative CHECK (chunk_index >= 0),
        CONSTRAINT document_chunks_tokens_positive CHECK (token_count > 0),
        CONSTRAINT document_chunks_content_nonempty CHECK (char_length(content) > 0)
    )
    """,
    "CREATE INDEX ix_document_chunks_workspace_id ON document_chunks (workspace_id)",
    "CREATE INDEX ix_document_chunks_document_id ON document_chunks (document_id)",
    """
    CREATE INDEX ix_document_chunks_embedding ON document_chunks
        USING hnsw (embedding vector_cosine_ops)
    """,
    # Forced RLS on document_chunks
    "ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE document_chunks FORCE ROW LEVEL SECURITY",
    """
    CREATE POLICY document_chunks_select ON document_chunks FOR SELECT
        USING (workspace_id = app_workspace_id())
    """,
    """
    CREATE POLICY document_chunks_insert ON document_chunks FOR INSERT
        WITH CHECK (workspace_id = app_workspace_id())
    """,
    """
    CREATE POLICY document_chunks_update ON document_chunks FOR UPDATE
        USING (workspace_id = app_workspace_id())
        WITH CHECK (workspace_id = app_workspace_id())
    """,
    """
    CREATE POLICY document_chunks_delete ON document_chunks FOR DELETE
        USING (workspace_id = app_workspace_id())
    """,
    # Least-privilege grants to the restricted application role
    f"GRANT SELECT, INSERT, UPDATE, DELETE ON documents TO {APP_ROLE}",
    f"GRANT SELECT, INSERT, UPDATE, DELETE ON document_chunks TO {APP_ROLE}",
]

_STATEMENTS_DOWN = [
    "DROP TABLE document_chunks",
    "DROP TABLE documents",
    "DROP EXTENSION IF EXISTS vector",
]


def upgrade() -> None:
    for statement in _STATEMENTS_UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _STATEMENTS_DOWN:
        op.execute(statement)
