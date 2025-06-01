-- Suna 开源版本数据库初始化脚本
-- 此脚本创建所有必要的表、索引、函数和权限

-- =============================================================================
-- 扩展和基础配置
-- =============================================================================

-- 启用必要的 PostgreSQL 扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- 创建应用程序用户
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'suna_app') THEN
        CREATE ROLE suna_app WITH LOGIN PASSWORD 'suna_app_password_2024';
    END IF;
END
$$;

-- 创建只读用户（用于 PostgREST）
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'suna_readonly') THEN
        CREATE ROLE suna_readonly WITH LOGIN PASSWORD 'suna_readonly_password_2024';
    END IF;
END
$$;

-- 创建 API 角色（用于 PostgREST）
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'suna_api') THEN
        CREATE ROLE suna_api NOLOGIN;
    END IF;
END
$$;

-- 创建匿名角色
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'suna_anon') THEN
        CREATE ROLE suna_anon NOLOGIN;
    END IF;
END
$$;

-- =============================================================================
-- Schema 创建
-- =============================================================================

-- 创建 auth schema（用于 GoTrue）
CREATE SCHEMA IF NOT EXISTS auth;

-- 授予权限
GRANT USAGE ON SCHEMA auth TO suna_app;
GRANT USAGE ON SCHEMA auth TO suna_readonly;
GRANT USAGE ON SCHEMA auth TO suna_api;
GRANT USAGE ON SCHEMA auth TO suna_anon;

-- =============================================================================
-- 账户和用户管理表
-- =============================================================================

-- 账户表（类似 Supabase 的 accounts）
CREATE TABLE IF NOT EXISTS accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    personal_account BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- 用户表（类似 GoTrue 的 users）
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    encrypted_password VARCHAR(255),
    email_confirmed_at TIMESTAMP WITH TIME ZONE,
    invited_at TIMESTAMP WITH TIME ZONE,
    confirmation_token VARCHAR(255),
    confirmation_sent_at TIMESTAMP WITH TIME ZONE,
    recovery_token VARCHAR(255),
    recovery_sent_at TIMESTAMP WITH TIME ZONE,
    email_change_token_new VARCHAR(255),
    email_change VARCHAR(255),
    email_change_sent_at TIMESTAMP WITH TIME ZONE,
    last_sign_in_at TIMESTAMP WITH TIME ZONE,
    raw_app_meta_data JSONB DEFAULT '{}',
    raw_user_meta_data JSONB DEFAULT '{}',
    is_super_admin BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    phone VARCHAR(15),
    phone_confirmed_at TIMESTAMP WITH TIME ZONE,
    phone_change VARCHAR(15),
    phone_change_token VARCHAR(255),
    phone_change_sent_at TIMESTAMP WITH TIME ZONE,
    confirmed_at TIMESTAMP WITH TIME ZONE GENERATED ALWAYS AS (LEAST(email_confirmed_at, phone_confirmed_at)) STORED,
    email_change_token_current VARCHAR(255) DEFAULT '',
    email_change_confirm_status SMALLINT DEFAULT 0,
    banned_until TIMESTAMP WITH TIME ZONE,
    reauthentication_token VARCHAR(255),
    reauthentication_sent_at TIMESTAMP WITH TIME ZONE,
    is_sso_user BOOLEAN DEFAULT false,
    deleted_at TIMESTAMP WITH TIME ZONE
);

-- 账户成员表
CREATE TABLE IF NOT EXISTS account_user (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_role VARCHAR(50) NOT NULL DEFAULT 'member',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(account_id, user_id)
);

-- =============================================================================
-- 核心业务表
-- =============================================================================

-- 项目表
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    is_public BOOLEAN DEFAULT false,
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 线程表
CREATE TABLE IF NOT EXISTS threads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name VARCHAR(255),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 消息表
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id UUID NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 代理运行表
CREATE TABLE IF NOT EXISTS agent_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id UUID NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    input JSONB DEFAULT '{}',
    output JSONB DEFAULT '{}',
    error_message TEXT,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 设备表（从原始迁移保留）
CREATE TABLE IF NOT EXISTS devices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    device_type VARCHAR(100),
    status VARCHAR(50) DEFAULT 'active',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 录制表（从原始迁移保留）
CREATE TABLE IF NOT EXISTS recordings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    device_id UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    name VARCHAR(255),
    file_path VARCHAR(500),
    duration INTEGER,
    size_bytes BIGINT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================================================
-- 索引
-- =============================================================================

-- 用户表索引
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_confirmation_token ON users(confirmation_token);
CREATE INDEX IF NOT EXISTS idx_users_recovery_token ON users(recovery_token);
CREATE INDEX IF NOT EXISTS idx_users_email_change_token_current ON users(email_change_token_current);
CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);

-- 账户表索引
CREATE INDEX IF NOT EXISTS idx_accounts_slug ON accounts(slug);

-- 账户成员表索引
CREATE INDEX IF NOT EXISTS idx_account_user_account_id ON account_user(account_id);
CREATE INDEX IF NOT EXISTS idx_account_user_user_id ON account_user(user_id);

-- 项目表索引
CREATE INDEX IF NOT EXISTS idx_projects_account_id ON projects(account_id);
CREATE INDEX IF NOT EXISTS idx_projects_is_public ON projects(is_public);

-- 线程表索引
CREATE INDEX IF NOT EXISTS idx_threads_project_id ON threads(project_id);

-- 消息表索引
CREATE INDEX IF NOT EXISTS idx_messages_thread_id ON messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);

-- 代理运行表索引
CREATE INDEX IF NOT EXISTS idx_agent_runs_thread_id ON agent_runs(thread_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status ON agent_runs(status);
CREATE INDEX IF NOT EXISTS idx_agent_runs_created_at ON agent_runs(created_at);

-- 设备表索引
CREATE INDEX IF NOT EXISTS idx_devices_account_id ON devices(account_id);

-- 录制表索引
CREATE INDEX IF NOT EXISTS idx_recordings_device_id ON recordings(device_id);

-- =============================================================================
-- 触发器函数
-- =============================================================================

-- 更新 updated_at 字段的触发器函数
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 为所有表创建 updated_at 触发器
DO $$
DECLARE
    t text;
BEGIN
    FOR t IN
        SELECT table_name 
        FROM information_schema.columns 
        WHERE column_name = 'updated_at' 
        AND table_schema = 'public'
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trigger_update_updated_at ON %I', t);
        EXECUTE format('CREATE TRIGGER trigger_update_updated_at 
                       BEFORE UPDATE ON %I 
                       FOR EACH ROW 
                       EXECUTE FUNCTION update_updated_at_column()', t);
    END LOOP;
END
$$;

-- =============================================================================
-- 行级安全策略 (RLS)
-- =============================================================================

-- 启用 RLS
ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE account_user ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE threads ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE recordings ENABLE ROW LEVEL SECURITY;

-- 创建获取当前用户 ID 的函数
CREATE OR REPLACE FUNCTION auth.uid() RETURNS UUID AS $$
  SELECT COALESCE(
    NULLIF(current_setting('request.jwt.claim.sub', true), ''),
    (NULLIF(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')
  )::uuid
$$ LANGUAGE SQL STABLE;

-- 创建检查用户角色的函数
CREATE OR REPLACE FUNCTION has_role_on_account(account_id UUID, required_role TEXT DEFAULT 'member')
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM account_user au
        WHERE au.account_id = $1
        AND au.user_id = auth.uid()
        AND (
            au.account_role = required_role
            OR (required_role = 'member' AND au.account_role IN ('admin', 'owner'))
            OR (required_role = 'admin' AND au.account_role = 'owner')
        )
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 账户策略
CREATE POLICY "Users can view accounts they belong to" ON accounts
    FOR SELECT USING (has_role_on_account(id));

CREATE POLICY "Users can update accounts they are admin of" ON accounts
    FOR UPDATE USING (has_role_on_account(id, 'admin'));

CREATE POLICY "Users can insert accounts" ON accounts
    FOR INSERT WITH CHECK (true);

-- 用户策略
CREATE POLICY "Users can view their own profile" ON users
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users can update their own profile" ON users
    FOR UPDATE USING (auth.uid() = id);

-- 账户成员策略
CREATE POLICY "Users can view account memberships" ON account_user
    FOR SELECT USING (has_role_on_account(account_id));

CREATE POLICY "Admins can manage account memberships" ON account_user
    FOR ALL USING (has_role_on_account(account_id, 'admin'));

-- 项目策略
CREATE POLICY "Users can view projects in their accounts or public projects" ON projects
    FOR SELECT USING (has_role_on_account(account_id) OR is_public = true);

CREATE POLICY "Users can insert projects in their accounts" ON projects
    FOR INSERT WITH CHECK (has_role_on_account(account_id));

CREATE POLICY "Users can update projects in their accounts" ON projects
    FOR UPDATE USING (has_role_on_account(account_id));

CREATE POLICY "Users can delete projects in their accounts" ON projects
    FOR DELETE USING (has_role_on_account(account_id));

-- 线程策略
CREATE POLICY "Users can view threads in accessible projects" ON threads
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM projects p 
            WHERE p.id = project_id 
            AND (has_role_on_account(p.account_id) OR p.is_public = true)
        )
    );

CREATE POLICY "Users can manage threads in their projects" ON threads
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM projects p 
            WHERE p.id = project_id 
            AND has_role_on_account(p.account_id)
        )
    );

-- 消息策略
CREATE POLICY "Users can view messages in accessible threads" ON messages
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM threads t
            JOIN projects p ON p.id = t.project_id
            WHERE t.id = thread_id 
            AND (has_role_on_account(p.account_id) OR p.is_public = true)
        )
    );

CREATE POLICY "Users can manage messages in their threads" ON messages
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM threads t
            JOIN projects p ON p.id = t.project_id
            WHERE t.id = thread_id 
            AND has_role_on_account(p.account_id)
        )
    );

-- 代理运行策略
CREATE POLICY "Users can view agent runs in accessible threads" ON agent_runs
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM threads t
            JOIN projects p ON p.id = t.project_id
            WHERE t.id = thread_id 
            AND (has_role_on_account(p.account_id) OR p.is_public = true)
        )
    );

CREATE POLICY "Users can manage agent runs in their threads" ON agent_runs
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM threads t
            JOIN projects p ON p.id = t.project_id
            WHERE t.id = thread_id 
            AND has_role_on_account(p.account_id)
        )
    );

-- 设备策略
CREATE POLICY "Users can view devices in their accounts" ON devices
    FOR SELECT USING (has_role_on_account(account_id));

CREATE POLICY "Users can manage devices in their accounts" ON devices
    FOR ALL USING (has_role_on_account(account_id));

-- 录制策略
CREATE POLICY "Users can view recordings of their devices" ON recordings
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM devices d 
            WHERE d.id = device_id 
            AND has_role_on_account(d.account_id)
        )
    );

CREATE POLICY "Users can manage recordings of their devices" ON recordings
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM devices d 
            WHERE d.id = device_id 
            AND has_role_on_account(d.account_id)
        )
    );

-- =============================================================================
-- 权限设置
-- =============================================================================

-- 授予应用程序用户权限
GRANT USAGE ON SCHEMA public TO suna_app;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO suna_app;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO suna_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO suna_app;

-- 授予只读用户权限
GRANT USAGE ON SCHEMA public TO suna_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO suna_readonly;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO suna_readonly;

-- 授予 API 角色权限（用于 PostgREST）
GRANT USAGE ON SCHEMA public TO suna_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO suna_api;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO suna_api;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO suna_api;

-- 授予匿名角色基本权限
GRANT USAGE ON SCHEMA public TO suna_anon;
GRANT SELECT ON projects TO suna_anon; -- 只能查看公开项目

-- 设置默认权限
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO suna_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO suna_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO suna_api;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO suna_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO suna_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO suna_api;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO suna_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO suna_api;

-- =============================================================================
-- 初始数据
-- =============================================================================

-- 创建默认的系统账户
INSERT INTO accounts (id, name, slug, personal_account, metadata) 
VALUES (
    '00000000-0000-0000-0000-000000000000',
    'System Account',
    'system',
    false,
    '{"description": "System account for administrative purposes"}'
) ON CONFLICT (id) DO NOTHING;

-- 创建默认的管理员用户（可选）
-- 注意：在生产环境中应该通过正常的注册流程创建用户
-- INSERT INTO users (id, email, encrypted_password, email_confirmed_at, raw_app_meta_data, raw_user_meta_data, is_super_admin)
-- VALUES (
--     '11111111-1111-1111-1111-111111111111',
--     'admin@suna.local',
--     crypt('admin_password_change_me', gen_salt('bf')),
--     NOW(),
--     '{"provider": "email", "providers": ["email"]}',
--     '{"name": "System Administrator"}',
--     true
-- ) ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- 完成
-- =============================================================================

-- 刷新权限
NOTIFY pgrst, 'reload schema';

-- 输出完成信息
DO $$
BEGIN
    RAISE NOTICE 'Suna 开源版本数据库初始化完成！';
    RAISE NOTICE '创建的表: accounts, users, account_user, projects, threads, messages, agent_runs, devices, recordings';
    RAISE NOTICE '创建的角色: suna_app, suna_readonly, suna_api, suna_anon';
    RAISE NOTICE '已启用行级安全策略 (RLS)';
    RAISE NOTICE '请确保更新应用程序配置以使用新的数据库连接信息';
END
$$;