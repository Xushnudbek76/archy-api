from alembic import op

revision = "0004_processing"
down_revision = "0003_duration_policy"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "\nCREATE TABLE archy.processing_provider_gate (\n\tmodel VARCHAR(80) NOT NULL, \n\tavailable_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tCONSTRAINT pk_processing_provider_gate PRIMARY KEY (model)\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE archy.processing_job (\n\tid UUID NOT NULL, \n\trecording_id UUID NOT NULL, \n\tstage VARCHAR(16) NOT NULL, \n\ttranscription_attempts INTEGER NOT NULL, \n\tsummary_attempts INTEGER NOT NULL, \n\tdeferrals INTEGER NOT NULL, \n\tlease_token UUID, \n\tlease_expires_at TIMESTAMP WITH TIME ZONE, \n\tavailable_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\terror_code VARCHAR(40) NOT NULL, \n\tprovider VARCHAR(16) NOT NULL, \n\ttranscription_model VARCHAR(80) NOT NULL, \n\tsummary_model VARCHAR(80) NOT NULL, \n\tprompt_version VARCHAR(16) NOT NULL, \n\tconfiguration JSONB NOT NULL, \n\tmanifest JSONB, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tCONSTRAINT pk_processing_job PRIMARY KEY (id), \n\tCONSTRAINT ck_processing_job_stage_valid CHECK (stage IN ('QUEUED','TRANSCRIBING','TRANSCRIBED','SUMMARIZING','COMPLETED','FAILED')), \n\tCONSTRAINT ck_processing_job_attempts_valid CHECK (transcription_attempts >= 0 AND summary_attempts >= 0 AND deferrals >= 0), \n\tCONSTRAINT ck_processing_job_lease_valid CHECK ((lease_token IS NULL) = (lease_expires_at IS NULL)), \n\tCONSTRAINT uq_processing_job_recording_id UNIQUE (recording_id), \n\tCONSTRAINT fk_processing_job_recording_id_recordings_recording FOREIGN KEY(recording_id) REFERENCES archy.recordings_recording (id) DEFERRABLE INITIALLY DEFERRED\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_processing_job_claim ON archy.processing_job (stage, available_at, lease_expires_at)"
    )
    op.execute(
        "\nCREATE TABLE archy.processing_note (\n\tid UUID NOT NULL, \n\tjob_id UUID NOT NULL, \n\tdocument JSONB NOT NULL, \n\tlanguage VARCHAR(2) NOT NULL, \n\tprovider VARCHAR(16) NOT NULL, \n\tmodel VARCHAR(80) NOT NULL, \n\tprompt_version VARCHAR(16) NOT NULL, \n\tCONSTRAINT pk_processing_note PRIMARY KEY (id), \n\tCONSTRAINT ck_processing_note_language_valid CHECK (language IN ('ko','en')), \n\tCONSTRAINT uq_processing_note_job_id UNIQUE (job_id), \n\tCONSTRAINT fk_processing_note_job_id_processing_job FOREIGN KEY(job_id) REFERENCES archy.processing_job (id) ON DELETE CASCADE\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE archy.processing_note_part (\n\tid UUID NOT NULL, \n\tjob_id UUID NOT NULL, \n\tlevel INTEGER NOT NULL, \n\tsequence INTEGER NOT NULL, \n\tsource_digest VARCHAR(64) NOT NULL, \n\tdocument JSONB NOT NULL, \n\tCONSTRAINT pk_processing_note_part PRIMARY KEY (id), \n\tCONSTRAINT uq_processing_note_part_job_id UNIQUE (job_id, level, sequence), \n\tCONSTRAINT fk_processing_note_part_job_id_processing_job FOREIGN KEY(job_id) REFERENCES archy.processing_job (id) ON DELETE CASCADE\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE archy.processing_transcript (\n\tid UUID NOT NULL, \n\tjob_id UUID NOT NULL, \n\ttext TEXT NOT NULL, \n\tsegments JSONB NOT NULL, \n\tlanguage VARCHAR(2) NOT NULL, \n\tprovider VARCHAR(16) NOT NULL, \n\tmodel VARCHAR(80) NOT NULL, \n\tCONSTRAINT pk_processing_transcript PRIMARY KEY (id), \n\tCONSTRAINT ck_processing_transcript_language_valid CHECK (language IN ('ko','en')), \n\tCONSTRAINT uq_processing_transcript_job_id UNIQUE (job_id), \n\tCONSTRAINT fk_processing_transcript_job_id_processing_job FOREIGN KEY(job_id) REFERENCES archy.processing_job (id) ON DELETE CASCADE\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE archy.processing_transcript_chunk (\n\tid UUID NOT NULL, \n\tjob_id UUID NOT NULL, \n\tsequence INTEGER NOT NULL, \n\tdocument JSONB NOT NULL, \n\tCONSTRAINT pk_processing_transcript_chunk PRIMARY KEY (id), \n\tCONSTRAINT uq_processing_transcript_chunk_job_id UNIQUE (job_id, sequence), \n\tCONSTRAINT fk_processing_transcript_chunk_job_id_processing_job FOREIGN KEY(job_id) REFERENCES archy.processing_job (id) ON DELETE CASCADE\n)\n\n"
    )


def downgrade():
    op.drop_table("processing_transcript_chunk", schema="archy")
    op.drop_table("processing_transcript", schema="archy")
    op.drop_table("processing_note_part", schema="archy")
    op.drop_table("processing_note", schema="archy")
    op.drop_table("processing_job", schema="archy")
    op.drop_table("processing_provider_gate", schema="archy")
