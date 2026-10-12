from alembic import op

revision = "0002_auth"
down_revision = "0001_legacy"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "\nCREATE TABLE archy.accounts_session (\n\tid UUID NOT NULL, \n\tuser_id UUID NOT NULL, \n\tdigest VARCHAR(64) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tCONSTRAINT pk_accounts_session PRIMARY KEY (id), \n\tCONSTRAINT fk_accounts_session_user_id_accounts_user FOREIGN KEY(user_id) REFERENCES archy.accounts_user (id) ON DELETE CASCADE, \n\tCONSTRAINT uq_accounts_session_digest UNIQUE (digest)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_accounts_session_expires_at ON archy.accounts_session (expires_at)")
    op.execute("CREATE INDEX ix_accounts_session_user_id ON archy.accounts_session (user_id)")
    op.execute(
        "\nCREATE TABLE archy.accounts_actiontoken (\n\tid UUID NOT NULL, \n\tuser_id UUID NOT NULL, \n\tsignup_attempt_id UUID, \n\tdigest VARCHAR(64) NOT NULL, \n\tpurpose VARCHAR(16) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tconsumed_at TIMESTAMP WITH TIME ZONE, \n\tCONSTRAINT pk_accounts_actiontoken PRIMARY KEY (id), \n\tCONSTRAINT fk_accounts_actiontoken_user_id_accounts_user FOREIGN KEY(user_id) REFERENCES archy.accounts_user (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_accounts_actiontoken_signup_attempt_id_accounts_sign_63a8 FOREIGN KEY(signup_attempt_id) REFERENCES archy.accounts_signupattempt (id) ON DELETE SET NULL, \n\tCONSTRAINT ck_accounts_actiontoken_purpose_valid CHECK (purpose IN ('confirm', 'reset')), \n\tCONSTRAINT uq_accounts_actiontoken_digest UNIQUE (digest)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_accounts_actiontoken_user_id ON archy.accounts_actiontoken (user_id)"
    )


def downgrade():
    raise RuntimeError("Auth downgrade requires a reviewed backup restoration.")
