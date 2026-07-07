from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260707_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("login", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("telegram_username", sa.String(64), nullable=True),
        sa.Column("device_limit", sa.Integer(), nullable=True),
        sa.Column("device_limit_unlimited", sa.Boolean(), nullable=False),
        sa.Column("show_server_support", sa.Boolean(), nullable=False),
        sa.Column("free_access", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.UniqueConstraint("login"),
    )
    op.create_index("ix_users_login", "users", ["login"])
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(80), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])

    op.create_table(
        "server_nodes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("public_host", sa.String(255), nullable=False),
        sa.Column("agent_base_url", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("public_port", sa.Integer(), nullable=True),
        sa.Column("region_note", sa.String(200), nullable=True),
        sa.Column("provider", sa.String(100), nullable=True),
        sa.Column("agent_key_id", sa.String(100), nullable=True),
        sa.Column("agent_secret_encrypted", sa.Text(), nullable=True),
        sa.Column("agent_allowed_ip_note", sa.String(200), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_status_payload", sa.JSON(), nullable=True),
        sa.Column("awg_container_name", sa.String(100), nullable=False),
        sa.Column("awg_interface", sa.String(50), nullable=False),
        sa.Column("awg_config_path", sa.String(255), nullable=False),
        sa.Column("clients_table_path", sa.String(255), nullable=False),
        sa.Column("is_available_for_new_devices", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
    )
    op.create_index("ix_server_nodes_status", "server_nodes", ["status"])

    op.create_table(
        "devices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("server_node_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=True),
        sa.Column("client_ip", sa.String(80), nullable=True),
        sa.Column("last_config_issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_handshake_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transfer_received_label", sa.String(100), nullable=True),
        sa.Column("transfer_sent_label", sa.String(100), nullable=True),
        sa.Column("last_agent_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_devices_user_id", "devices", ["user_id"])
    op.create_index("ix_devices_server_node_id", "devices", ["server_node_id"])
    op.create_index("ix_devices_status", "devices", ["status"])

    op.create_table(
        "device_config_issues",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("issued_to_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("config_encrypted", sa.Text(), nullable=True),
        sa.Column("vpn_url_encrypted", sa.Text(), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("device_id"),
    )
    op.create_index(
        "ix_device_config_issues_device_id", "device_config_issues", ["device_id"]
    )
    op.create_index(
        "ix_device_config_issues_issued_to_user_id",
        "device_config_issues",
        ["issued_to_user_id"],
    )
    op.create_index(
        "ix_device_config_issues_expires_at", "device_config_issues", ["expires_at"]
    )

    op.create_table(
        "support_contributions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("recorded_by_user_id", sa.String(36), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_label", sa.String(64), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
    )
    op.create_index("ix_support_contributions_user_id", "support_contributions", ["user_id"])
    op.create_index(
        "ix_support_contributions_recorded_at",
        "support_contributions",
        ["recorded_at"],
    )

    op.create_table(
        "support_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("sbp_phone", sa.String(100), nullable=True),
        sa.Column("bank_name", sa.String(100), nullable=True),
        sa.Column("extra_contact", sa.Text(), nullable=True),
        sa.Column("monthly_cost_amount", sa.Float(), nullable=True),
        sa.Column("reserve_amount", sa.Float(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_by_user_id", sa.String(36), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "setup_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("server_name", sa.String(100), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("ssh_port", sa.Integer(), nullable=False),
        sa.Column("ssh_username", sa.String(64), nullable=False),
        sa.Column("auth_method", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=True),
        sa.Column("region_note", sa.String(200), nullable=True),
        sa.Column("install_awg", sa.Boolean(), nullable=False),
        sa.Column("available_for_new_devices", sa.Boolean(), nullable=False),
        sa.Column("verify_before_install", sa.Boolean(), nullable=False),
        sa.Column("current_step", sa.String(100), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("server_node_id", sa.String(36), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_setup_jobs_created_by_user_id", "setup_jobs", ["created_by_user_id"])
    op.create_index("ix_setup_jobs_status", "setup_jobs", ["status"])

    op.create_table(
        "setup_job_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("setup_job_id", sa.String(36), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("step", sa.String(50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
    )
    op.create_index("ix_setup_job_events_setup_job_id", "setup_job_events", ["setup_job_id"])
    op.create_index("ix_setup_job_events_created_at", "setup_job_events", ["created_at"])

    op.create_table(
        "audit_log_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=True),
        sa.Column("target_type", sa.String(60), nullable=True),
        sa.Column("target_id", sa.String(36), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("ip_address", sa.String(80), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
    )
    op.create_index("ix_audit_log_entries_action", "audit_log_entries", ["action"])
    op.create_index("ix_audit_log_entries_created_at", "audit_log_entries", ["created_at"])

    op.create_table(
        "login_failures",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(160), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_login_failures_key", "login_failures", ["key"])
    op.create_index("ix_login_failures_attempted_at", "login_failures", ["attempted_at"])


def downgrade() -> None:
    for table in (
        "login_failures",
        "audit_log_entries",
        "setup_job_events",
        "setup_jobs",
        "support_settings",
        "support_contributions",
        "device_config_issues",
        "devices",
        "server_nodes",
        "sessions",
        "users",
    ):
        op.drop_table(table)
