# -*- coding: utf-8 -*-
from sqlalchemy import create_engine, text, Column, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker, declarative_base
from logger import logger
from config import Config

Base = declarative_base()

class DocumentStore(Base):
    """通用文档表，每个collection对应一张表"""
    __abstract__ = True

    id = Column(String, primary_key=True)
    data = Column(JSONB, nullable=False)

class Database:
    _engine = None
    _session_factory = None

    # 需要的"集合"名，对应建表
    COLLECTIONS = [
          # 现有业务表
          "files",
          "sessions",
          "memories",
          "config",
          # 配置表 - 系统配置
          "model_connections",
          "model_levels",
          "gateway_env",
          "gateway_apps",
          "gateway_channels",
          "tools",
          "chat_logs",
          # 配置表 - 业务配置
          "roles",
          "sub_agents",
          "skills",
          "file_processing",
          "scenes",
      ]


    @classmethod
    def connect(cls):
        if cls._engine is None:
            try:
                cls._engine = create_engine(Config.PG_URI)
                cls._session_factory = sessionmaker(bind=cls._engine)

                # 测试连接
                with cls._engine.connect() as conn:
                    conn.execute(text("SELECT 1"))

                cls._init_tables()
                logger.info("Connected to PostgreSQL and tables initialized.")
            except Exception as e:
                logger.error(f"PostgreSQL Connection Error: {e}")
                raise e

    @classmethod
    def _init_tables(cls):
        try:
            with cls._engine.connect() as conn:
                for col in cls.COLLECTIONS:
                    conn.execute(text(f"""
                        CREATE TABLE IF NOT EXISTS {col} (
                            id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::varchar,
                            data JSONB NOT NULL DEFAULT '{{}}'::jsonb
                        )
                    """))

                # 现有业务表索引
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_files_file_id ON files ((data->>'file_id'));
                    CREATE INDEX IF NOT EXISTS idx_sessions_session_id ON sessions ((data->>'session_id'));
                    CREATE INDEX IF NOT EXISTS idx_memories_session_id ON memories ((data->>'session_id'));
                    CREATE INDEX IF NOT EXISTS idx_memories_timestamp ON memories ((data->>'timestamp'));
                    CREATE INDEX IF NOT EXISTS idx_files_app_id ON files ((data->>'app_id'));
                    CREATE INDEX IF NOT EXISTS idx_sessions_app_id ON sessions ((data->>'app_id'));
                    CREATE INDEX IF NOT EXISTS idx_memories_app_id ON memories ((data->>'app_id'));
                """))

                # 配置表索引
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_model_connections_protocol ON model_connections ((data->>'protocol'));
                    CREATE INDEX IF NOT EXISTS idx_model_levels_level ON model_levels ((data->>'level'));
                    CREATE INDEX IF NOT EXISTS idx_model_levels_connection_id ON model_levels ((data->>'connection_id'));
                    CREATE INDEX IF NOT EXISTS idx_gateway_apps_app_id ON gateway_apps ((data->>'app_id'));
                    CREATE INDEX IF NOT EXISTS idx_tools_type ON tools ((data->>'type'));
                    CREATE INDEX IF NOT EXISTS idx_tools_enabled ON tools ((data->>'enabled'));
                    CREATE INDEX IF NOT EXISTS idx_chat_logs_app_id ON chat_logs ((data->>'app_id'));
                    CREATE INDEX IF NOT EXISTS idx_chat_logs_session_id ON chat_logs ((data->>'session_id'));
                    CREATE INDEX IF NOT EXISTS idx_chat_logs_scene_id ON chat_logs ((data->>'scene_id'));
                    CREATE INDEX IF NOT EXISTS idx_roles_name ON roles ((data->>'name'));
                    CREATE INDEX IF NOT EXISTS idx_sub_agents_name ON sub_agents ((data->>'name'));
                    CREATE INDEX IF NOT EXISTS idx_skills_name ON skills ((data->>'name'));
                    CREATE INDEX IF NOT EXISTS idx_scenes_scene_code ON scenes ((data->>'scene_code'));
                """))
                conn.commit()
                logger.info("PostgreSQL tables and indices ensured.")
        except Exception as e:
            logger.warning(f"Could not create tables: {e}")


    @classmethod
    def get_session(cls):
        if cls._session_factory is None:
            cls.connect()
        return cls._session_factory()
