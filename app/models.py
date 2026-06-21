from sqlalchemy import Column, Integer, String, Float, DateTime, Index
from app.database import Base

class SearchQuery(Base):
    __tablename__ = "search_queries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query_text = Column(String(255), unique=True, nullable=False, index=True)
    global_count = Column(Integer, default=0, nullable=False, index=True)
    weekly_count = Column(Integer, default=0, nullable=False)
    daily_count = Column(Integer, default=0, nullable=False)
    trending_score = Column(Float, default=0.0, nullable=False, index=True)

    # Composite index for prefix search on query_text + sorting by trending_score
    __table_args__ = (
        Index("idx_query_trending", "query_text", "trending_score"),
    )

    def __repr__(self) -> str:
        return f"<SearchQuery(query_text='{self.query_text}', global_count={self.global_count}, trending_score={self.trending_score})>"


class QueryLog(Base):
    __tablename__ = "query_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query_text = Column(String(255), nullable=False, index=True)
    query_time = Column(DateTime, nullable=False, index=True)

    # Composite index for calculating rolling query counts (daily and weekly counts)
    __table_args__ = (
        Index("idx_log_query_time", "query_text", "query_time"),
    )

    def __repr__(self) -> str:
        return f"<QueryLog(query_text='{self.query_text}', query_time='{self.query_time}')>"
