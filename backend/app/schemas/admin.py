"""
AI Fitness Coach v1 — Admin Schemas

Request/response models for import/restore operations.
"""
from pydantic import BaseModel, Field
from typing import Optional, Any
from enum import Enum


class RestoreMode(str, Enum):
    """Mode for restore operation."""
    replace = "replace"  # Delete existing, restore from bundle
    merge = "merge"      # Add new records only, skip existing


class EntityPreview(BaseModel):
    """Preview for a single entity type."""
    action: str  # "create" | "update" | "skip"
    exists: bool


class CollectionPreview(BaseModel):
    """Preview for a collection of records."""
    count: int
    new: int
    existing: int


class ImportPreview(BaseModel):
    """Preview of what will be restored."""
    user: EntityPreview
    profile: EntityPreview
    weight_entries: CollectionPreview
    plans: CollectionPreview
    revisions: CollectionPreview
    workout_logs: CollectionPreview
    adherence_records: CollectionPreview


class ImportPreviewRequest(BaseModel):
    """Request to preview an import operation."""
    bundle: dict = Field(..., description="The audit bundle JSON to import")
    target_user_id: Optional[str] = Field(
        None,
        description="Override the user ID (restores to different user)"
    )


class ImportPreviewResponse(BaseModel):
    """Response from import preview."""
    valid: bool
    bundle_version: Optional[str] = None
    source_user_id: Optional[str] = None
    target_user_id: Optional[str] = None
    exported_at: Optional[str] = None

    preview: Optional[ImportPreview] = None
    conflicts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    dry_run_available: bool = True


class EntityResult(BaseModel):
    """Result for a single entity operation."""
    action: str  # "created" | "updated" | "skipped"
    success: bool


class CollectionResult(BaseModel):
    """Result for a collection of records."""
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0


class ImportResults(BaseModel):
    """Results of import operation by entity type."""
    user: EntityResult
    profile: EntityResult
    weight_entries: CollectionResult
    plans: CollectionResult
    revisions: CollectionResult
    workout_logs: CollectionResult
    adherence_records: CollectionResult


class ImportRestoreRequest(BaseModel):
    """Request to restore from an audit bundle."""
    bundle: dict = Field(..., description="The audit bundle JSON to import")
    mode: RestoreMode = Field(
        RestoreMode.merge,
        description="replace: delete existing first, merge: add new only"
    )
    dry_run: bool = Field(
        False,
        description="If true, validate without committing changes"
    )
    target_user_id: Optional[str] = Field(
        None,
        description="Override the user ID (restores to different user)"
    )


class ImportRestoreResponse(BaseModel):
    """Response from restore operation."""
    success: bool
    mode: str
    dry_run: bool
    target_user_id: str
    backup_id: Optional[str] = None  # Only for replace mode

    results: Optional[ImportResults] = None
    errors: list[str] = Field(default_factory=list)
    message: str
