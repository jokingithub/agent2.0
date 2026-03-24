-- 启用向量扩展（pgvector）
CREATE EXTENSION IF NOT EXISTS vector;

-- 可选：常用扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;
