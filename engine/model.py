"""
model.py
--------
SQLAlchemy ORM models for persisting classified document data in SQLite.

Schema overview:
  ┌──────────────┐
  │   customers  │  ← base entity; every document links back here
  └──────┬───────┘
         │ 1
         ├──────────────── * ─── id_documents    (Aadhaar, Passport, DL, Voter ID)
         │                       PK = document_id
         │
         ├──────────────── * ─── pan_cards        (PAN — separate table, PK = pan_no)
         │
         ├──────────────── * ─── bank_accounts    (bank account details, PK = account_no)
         │
         └──────────────── * ─── document_chunks  (vector-DB refs for detailed docs:
                                                   invoices, bank statements,
                                                   insurance receipts, road-tax receipts)
                                 PK = chunk_id, FK = customer_id

Design notes:
  • ID documents (Aadhaar, Passport, DL, Voter ID) share identical fields
    (name, DOB, address, document_type, document_id) so they live in one table
    with `document_type` as a discriminator.
  • PAN has a distinct identifier format (AAAAA9999A) that is best served as its
    own primary key (`pan_no`), hence a dedicated table.
  • Detailed / unstructured documents (bank statements, invoices, insurance,
    road-tax receipts) are chunked for vector search; only metadata is stored
    here — the actual embeddings live in the vector DB.
"""

from datetime import datetime, date

from sqlalchemy import (
    Column, String, Date, DateTime, Text, ForeignKey, Enum, create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
import enum
Base = declarative_base()

DATABASE_URL = "sqlite:///doc_classifier.db"

engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class IDDocumentType(str, enum.Enum):
    AADHAAR   = "AADHAAR"
    PASSPORT  = "PASSPORT"
    DL        = "DL"
    VOTER_ID  = "VOTER_ID"


class DetailedDocumentType(str, enum.Enum):
    BANK_STATEMENT = "BANK_STATEMENT"
    BANK_PASSBOOK  = "BANK_PASSBOOK"
    CHEQUE         = "CHEQUE"
    INVOICE        = "INVOICE"
    INSURANCE      = "INSURANCE"
    ROAD_TAX       = "ROAD_TAX"


class Customer(Base):
    __tablename__ = "customers"
    customer_id = Column(String(36), primary_key=True, comment="UUID or external ID")
    name        = Column(String(255), nullable=False)
    email       = Column(String(255), nullable=True)
    phone       = Column(String(20), nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)

    id_documents    = relationship("IDDocument",    back_populates="customer", cascade="all, delete-orphan")
    pan_cards       = relationship("PANCard",       back_populates="customer", cascade="all, delete-orphan")
    bank_accounts   = relationship("BankAccount",   back_populates="customer", cascade="all, delete-orphan")
    document_chunks = relationship("DocumentChunk", back_populates="customer", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Customer {self.customer_id} — {self.name}>"



class IDDocument(Base):
    __tablename__ = "id_documents"
    document_id   = Column(String(20), primary_key=True,
                           comment="Aadhaar (12 digits) / Passport (8 chars) / DL (15 chars) / Voter ID (10 chars)")
    customer_id   = Column(String(36), ForeignKey("customers.customer_id"), nullable=False, index=True)
    document_type = Column(Enum(IDDocumentType), nullable=False, index=True,
                           comment="AADHAAR | PASSPORT | DL | VOTER_ID")
    name          = Column(String(255), nullable=True, comment="Name as printed on the document")
    date_of_birth = Column(Date,        nullable=True)
    address       = Column(Text,        nullable=True, comment="Full address from the document")
    gender        = Column(String(10),  nullable=True)
    issue_date    = Column(Date,        nullable=True, comment="Date of issue (DL / Passport)")
    expiry_date   = Column(Date,        nullable=True, comment="Expiry date (DL / Passport)")
    created_at    = Column(DateTime,    default=datetime.utcnow)
    customer = relationship("Customer", back_populates="id_documents")

    def __repr__(self):
        return f"<IDDocument {self.document_type.value}: {self.document_id}>"
class PANCard(Base):
    __tablename__ = "pan_cards"
    pan_no        = Column(String(10), primary_key=True, comment="AAAAA9999A format")
    customer_id   = Column(String(36), ForeignKey("customers.customer_id"), nullable=False, index=True)
    name          = Column(String(255), nullable=True, comment="Name as printed on the PAN card")
    father_name   = Column(String(255), nullable=True, comment="Father's name (printed on PAN)")
    date_of_birth = Column(Date,        nullable=True)
    holder_type   = Column(String(1),   nullable=True,
                           comment="4th char of PAN — P(Individual), C(Company), H(HUF), etc.")
    created_at    = Column(DateTime,    default=datetime.utcnow)
    customer = relationship("Customer", back_populates="pan_cards")

    def __repr__(self):
        return f"<PANCard {self.pan_no}>"

class BankAccount(Base):
    __tablename__ = "bank_accounts"

    account_no   = Column(String(20), primary_key=True, comment="Bank account number")
    customer_id  = Column(String(36), ForeignKey("customers.customer_id"), nullable=False, index=True)
    account_name = Column(String(255), nullable=True, comment="Account holder name (if available)")
    bank_name    = Column(String(255), nullable=True, comment="Name of the bank")
    ifsc_code    = Column(String(11),  nullable=True, comment="IFSC code (11 chars: AAAA0XXXXXX)")
    branch       = Column(String(255), nullable=True, comment="Branch name")
    account_type = Column(String(20),  nullable=True, comment="Savings / Current / etc.")
    created_at   = Column(DateTime,    default=datetime.utcnow)
    customer = relationship("Customer", back_populates="bank_accounts")

    def __repr__(self):
        return f"<BankAccount {self.account_no} — {self.bank_name}>"

class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    chunk_id       = Column(String(64), primary_key=True, comment="Unique chunk ID matching the vector DB entry")
    customer_id    = Column(String(36), ForeignKey("customers.customer_id"), nullable=False, index=True)
    document_type  = Column(Enum(DetailedDocumentType), nullable=False, index=True,
                            comment="BANK_STATEMENT | BANK_PASSBOOK | CHEQUE | INVOICE | INSURANCE | ROAD_TAX")
    source_file    = Column(String(512), nullable=True, comment="Original filename / path of the uploaded document")
    page_number    = Column(String(10),  nullable=True, comment="Page number within the source PDF")
    chunk_text     = Column(Text,        nullable=True, comment="Plain-text content of this chunk (for debugging / display)")
    created_at     = Column(DateTime,    default=datetime.utcnow)
    customer = relationship("Customer", back_populates="document_chunks")

    def __repr__(self):
        return f"<DocumentChunk {self.chunk_id} — {self.document_type.value}>"


def init_db():
    Base.metadata.create_all(bind=engine)


def get_session():
    return SessionLocal()
if __name__ == "__main__":
    init_db()
    print(f"Database created at {DATABASE_URL}")
    print("Tables:")
    for table in Base.metadata.sorted_tables:
        cols = ", ".join(c.name for c in table.columns)
        print(f"• {table.name}  ({cols})")
