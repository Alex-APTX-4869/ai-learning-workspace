from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base


class DraftMaterialBinding(Base):
    __tablename__ = 'directory_draft_materials'
    # 一批资料只允许被一个局部修订认领；发布后沿版本链继承。
    batch_id: Mapped[str] = mapped_column(ForeignKey('material_batches.id'), primary_key=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey('directory_drafts.id'), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey('courses.id'), index=True)
