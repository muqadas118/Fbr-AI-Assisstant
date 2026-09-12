"""
Document Storage - Production-Grade
====================================

In-memory document storage with metadata, versioning, and search.
In production, would use:
- AWS S3 / Azure Blob for binary
- PostgreSQL for metadata
- Elasticsearch for full-text search
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

logger = logging.getLogger("document_intelligence")


class DocumentStatus(str, Enum):
    """Document processing status."""
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    ANALYZED = "analyzed"
    FAILED = "failed"
    ARCHIVED = "archived"


@dataclass
class StoredDocument:
    """A document stored in the system."""
    id: str
    user_id: str
    filename: str
    file_size: int
    file_type: str  # pdf, jpg, png, etc.
    content_hash: str  # SHA256 of file

    # Storage
    storage_path: str = ""
    storage_url: str = ""

    # Processing
    status: DocumentStatus = DocumentStatus.UPLOADED
    document_type: str = "unknown"
    category: str = "other"
    analysis_id: Optional[str] = None
    classification_confidence: float = 0.0

    # Metadata
    tags: list[str] = field(default_factory=list)
    related_to: list[str] = field(default_factory=list)  # NTN, CNIC, etc.
    tax_year: Optional[int] = None
    amount: Optional[float] = None

    # Versioning
    version: int = 1
    parent_id: Optional[str] = None

    # Timestamps
    uploaded_at: str = ""
    processed_at: Optional[str] = None
    last_accessed: Optional[str] = None
    access_count: int = 0

    # Notes
    description: str = ""
    user_notes: str = ""

    def __post_init__(self):
        if not self.uploaded_at:
            self.uploaded_at = datetime.utcnow().isoformat()


class DocumentStore:
    """In-memory document store."""

    def __init__(self):
        self.documents: dict[str, StoredDocument] = {}
        self.index_by_user: dict[str, set[str]] = {}
        self.index_by_type: dict[str, set[str]] = {}
        self.index_by_tag: dict[str, set[str]] = {}

    def store(
        self,
        user_id: str,
        filename: str,
        file_size: int,
        file_type: str,
        content_hash: str,
        **kwargs,
    ) -> StoredDocument:
        """Store a new document."""
        doc_id = str(uuid.uuid4())
        doc = StoredDocument(
            id=doc_id,
            user_id=user_id,
            filename=filename,
            file_size=file_size,
            file_type=file_type,
            content_hash=content_hash,
            **kwargs,
        )

        self.documents[doc_id] = doc

        # Update indexes
        if user_id not in self.index_by_user:
            self.index_by_user[user_id] = set()
        self.index_by_user[user_id].add(doc_id)

        if doc.document_type not in self.index_by_type:
            self.index_by_type[doc.document_type] = set()
        self.index_by_type[doc.document_type].add(doc_id)

        for tag in doc.tags:
            if tag not in self.index_by_tag:
                self.index_by_tag[tag] = set()
            self.index_by_tag[tag].add(doc_id)

        logger.info(f"Stored document: {doc_id} - {filename}")
        return doc

    def get(self, doc_id: str) -> Optional[StoredDocument]:
        """Get document by ID."""
        doc = self.documents.get(doc_id)
        if doc:
            doc.access_count += 1
            doc.last_accessed = datetime.utcnow().isoformat()
        return doc

    def get_by_user(self, user_id: str) -> list[StoredDocument]:
        """Get all documents for a user."""
        doc_ids = self.index_by_user.get(user_id, set())
        return [self.documents[did] for did in doc_ids if did in self.documents]

    def get_by_type(self, document_type: str) -> list[StoredDocument]:
        """Get documents by type."""
        doc_ids = self.index_by_type.get(document_type, set())
        return [self.documents[did] for did in doc_ids if did in self.documents]

    def get_by_tag(self, tag: str) -> list[StoredDocument]:
        """Get documents by tag."""
        doc_ids = self.index_by_tag.get(tag, set())
        return [self.documents[did] for did in doc_ids if did in self.documents]

    def search(
        self,
        user_id: Optional[str] = None,
        document_type: Optional[str] = None,
        tag: Optional[str] = None,
        tax_year: Optional[int] = None,
        min_amount: Optional[float] = None,
        max_amount: Optional[float] = None,
    ) -> list[StoredDocument]:
        """Search documents with filters."""
        results = list(self.documents.values())

        if user_id:
            results = [d for d in results if d.user_id == user_id]
        if document_type:
            results = [d for d in results if d.document_type == document_type]
        if tag:
            results = [d for d in results if tag in d.tags]
        if tax_year:
            results = [d for d in results if d.tax_year == tax_year]
        if min_amount is not None:
            results = [d for d in results if d.amount and d.amount >= min_amount]
        if max_amount is not None:
            results = [d for d in results if d.amount and d.amount <= max_amount]

        return results

    def update(self, doc_id: str, **kwargs) -> Optional[StoredDocument]:
        """Update document metadata."""
        doc = self.documents.get(doc_id)
        if not doc:
            return None

        for key, value in kwargs.items():
            if hasattr(doc, key):
                setattr(doc, key, value)

        # Re-index if type changed
        if "document_type" in kwargs:
            new_type = kwargs["document_type"]
            for old_type, ids in self.index_by_type.items():
                if doc_id in ids:
                    ids.discard(doc_id)
            if new_type not in self.index_by_type:
                self.index_by_type[new_type] = set()
            self.index_by_type[new_type].add(doc_id)

        return doc

    def delete(self, doc_id: str) -> bool:
        """Delete document."""
        doc = self.documents.get(doc_id)
        if not doc:
            return False

        # Remove from indexes
        if doc.user_id in self.index_by_user:
            self.index_by_user[doc.user_id].discard(doc_id)
        if doc.document_type in self.index_by_type:
            self.index_by_type[doc.document_type].discard(doc_id)
        for tag in doc.tags:
            if tag in self.index_by_tag:
                self.index_by_tag[tag].discard(doc_id)

        del self.documents[doc_id]
        logger.info(f"Deleted document: {doc_id}")
        return True

    def get_stats(self, user_id: Optional[str] = None) -> dict:
        """Get storage statistics."""
        docs = (
            [d for d in self.documents.values() if d.user_id == user_id]
            if user_id
            else list(self.documents.values())
        )

        return {
            "total_documents": len(docs),
            "total_size_bytes": sum(d.file_size for d in docs),
            "by_type": {
                t: len([d for d in docs if d.document_type == t])
                for t in set(d.document_type for d in docs)
            },
            "by_status": {
                s.value: len([d for d in docs if d.status == s])
                for s in DocumentStatus
            },
            "total_value": sum(d.amount or 0 for d in docs),
        }


# Singleton
_store: Optional[DocumentStore] = None


def get_document_store() -> DocumentStore:
    """Get singleton document store."""
    global _store
    if _store is None:
        _store = DocumentStore()
    return _store
