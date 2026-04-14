from dataclasses import dataclass, field
from typing import List, Optional, Any
from datetime import datetime


@dataclass
class AuthResponse:
    token: str
    expires: str

    @classmethod
    def from_dict(cls, data: dict) -> "AuthResponse":
        return cls(
            token=data.get("token", ""),
            expires=data.get("expires", "")
        )


@dataclass
class DataRecord:
    id: str
    type: str
    data: dict
    created_at: str

    @classmethod
    def from_dict(cls, data: dict) -> "DataRecord":
        return cls(
            id=data.get("id", ""),
            type=data.get("type", ""),
            data=data.get("data", {}),
            created_at=data.get("created_at", "")
        )


@dataclass
class DataResponse:
    data: List[DataRecord]
    has_more: bool
    sync_token: str

    @classmethod
    def from_dict(cls, data: dict) -> "DataResponse":
        records = [DataRecord.from_dict(r) for r in data.get("data", [])]
        return cls(
            data=records,
            has_more=data.get("has_more", False),
            sync_token=data.get("sync_token", "")
        )


@dataclass
class InvoiceItem:
    name: str
    quantity: float
    price: float
    amount: float
    vat_rate: Optional[float] = None
    vat_amount: Optional[float] = None

    @classmethod
    def from_dict(cls, data: dict) -> "InvoiceItem":
        return cls(
            name=data.get("name", ""),
            quantity=data.get("quantity", 0.0),
            price=data.get("price", 0.0),
            amount=data.get("amount", 0.0),
            vat_rate=data.get("vat_rate") if "vat_rate" in data else (data.get("vatRate") if "vatRate" in data else None),
            vat_amount=data.get("vat_amount") if "vat_amount" in data else (data.get("vatAmount") if "vatAmount" in data else None)
        )


@dataclass
class Invoice:
    id: str
    number: str
    date: str
    counterparty_id: str
    counterparty_name: str
    amount: float
    currency: str
    status: str
    items: List[InvoiceItem] = field(default_factory=list)
    pdf: Optional[str] = None
    counterparty: Optional[dict] = None
    vat: Optional[float] = None
    paid_amount: Optional[float] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Invoice":
        items = [InvoiceItem.from_dict(i) for i in data.get("items", [])]

        counterparty_id = ""
        counterparty_name = ""
        if "counterparty" in data and isinstance(data["counterparty"], dict):
            counterparty_id = data["counterparty"].get("id", "")
            counterparty_name = data["counterparty"].get("name", "")
        else:
            counterparty_id = data.get("counterparty_id", "")
            counterparty_name = data.get("counterparty_name", "")
        
        return cls(
            id=data.get("id", ""),
            number=data.get("number", ""),
            date=data.get("date", ""),
            counterparty_id=counterparty_id,
            counterparty_name=counterparty_name,
            amount=data.get("amount", 0.0),
            currency=data.get("currency", "KZT"),
            status=data.get("status", ""),
            items=items,
            pdf=data.get("pdf"),
            counterparty=data.get("counterparty") if isinstance(data.get("counterparty"), dict) else None,
            vat=data.get("vat"),
            paid_amount=data.get("paid_amount")
        )


@dataclass
class Payment:
    id: str
    type: str
    number: str
    date: str
    counterparty_id: str
    counterparty_name: str
    amount: float
    currency: str
    purpose: str

    @classmethod
    def from_dict(cls, data: dict) -> "Payment":
        return cls(
            id=data.get("id", ""),
            type=data.get("type", ""),
            number=data.get("number", ""),
            date=data.get("date", ""),
            counterparty_id=data.get("counterparty_id", ""),
            counterparty_name=data.get("counterparty_name", ""),
            amount=data.get("amount", 0.0),
            currency=data.get("currency", "KZT"),
            purpose=data.get("purpose", "")
        )


@dataclass
class AgingDetail:
    period: str
    amount: float

    @classmethod
    def from_dict(cls, data: dict) -> "AgingDetail":
        return cls(
            period=data.get("period", ""),
            amount=data.get("amount", 0.0)
        )


@dataclass
class BalanceDetail:
    receivable: float
    payable: float
    net: float

    @classmethod
    def from_dict(cls, data: dict) -> "BalanceDetail":
        return cls(
            receivable=data.get("receivable", 0.0),
            payable=data.get("payable", 0.0),
            net=data.get("net", 0.0)
        )


@dataclass
class Balance:
    counterparty: dict
    balances: BalanceDetail
    aging: List[Any]
    documents: List[dict] = field(default_factory=list)
    by_documents: List[dict] = field(default_factory=list)
    date: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Balance":

        by_documents = data.get("by_documents", [])
        

        balances_data = data.get("balances", {})
        if not balances_data and by_documents:

            receivable = sum(doc.get("debt", 0) for doc in by_documents if doc.get("debt", 0) > 0)
            payable = abs(sum(doc.get("debt", 0) for doc in by_documents if doc.get("debt", 0) < 0))
            net = receivable - payable
            balances = BalanceDetail(
                receivable=receivable,
                payable=payable,
                net=net
            )
        elif isinstance(balances_data, dict):
            balances = BalanceDetail.from_dict(balances_data)
        else:
            balances = BalanceDetail(receivable=0.0, payable=0.0, net=0.0)
        

        raw_aging = data.get("aging", [])
        aging = []
        for a in raw_aging:
            if isinstance(a, dict):
                aging.append(AgingDetail.from_dict(a))
            else:
                aging.append(a)
        

        documents = data.get("documents", [])
        if not documents and by_documents:
            documents = by_documents
        
        return cls(
            counterparty=data.get("counterparty", {}),
            balances=balances,
            aging=aging,
            documents=documents,
            by_documents=by_documents,
            date=data.get("date")
        )


@dataclass
class BankAccount:
    id: str
    bank_name: str
    bank_bik: str
    account_number: str
    currency: str
    is_default: bool

    @classmethod
    def from_dict(cls, data: dict) -> "BankAccount":
        return cls(
            id=data.get("id", ""),
            bank_name=data.get("bank_name", ""),
            bank_bik=data.get("bank_bik", ""),
            account_number=data.get("account_number", ""),
            currency=data.get("currency", "KZT"),
            is_default=data.get("is_default", False)
        )


@dataclass
class Contract:
    id: str
    number: str
    date: str
    name: str
    type: str

    @classmethod
    def from_dict(cls, data: dict) -> "Contract":
        return cls(
            id=data.get("id", ""),
            number=data.get("number", ""),
            date=data.get("date", ""),
            name=data.get("name", ""),
            type=data.get("type", "")
        )


@dataclass
class Counterparty:
    id: str
    full_name: str
    short_name: str = ""
    bin: str = ""
    address: str = ""
    phone: str = ""
    phone_number: str = ""
    email: str = ""
    is_supplier: bool = False
    is_customer: bool = False
    bank_accounts: List[BankAccount] = field(default_factory=list)
    contracts: List[Contract] = field(default_factory=list)

    gov_entity: bool = False
    vat_cert_date: str = ""
    kbe: str = ""
    vat_cert_no: str = ""
    rnn: str = ""
    vat_series: str = ""
    residency_country: str = ""
    counterparty_type: str = ""
    account_number: str = ""
    bic: str = ""
    contract_number: str = ""
    contract_date: str = ""
    currency: str = ""
    price_type: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Counterparty":

        bank_accounts = []
        if "bankAccounts" in data or "bank_accounts" in data:
            bank_accounts = [BankAccount.from_dict(b) for b in data.get("bankAccounts", data.get("bank_accounts", []))]
        elif "accountNumber" in data and data.get("accountNumber"):

            bank_accounts = [BankAccount(
                id=data.get("id", ""),
                bank_name="",
                bank_bik=data.get("bic", ""),
                account_number=data.get("accountNumber", ""),
                currency=data.get("currency", "KZT"),
                is_default=True
            )]
        

        contracts = []
        if "contracts" in data:
            contracts = [Contract.from_dict(c) for c in data.get("contracts", [])]
        elif "contractNumber" in data and data.get("contractNumber"):

            contracts = [Contract(
                id=data.get("id", ""),
                number=data.get("contractNumber", ""),
                date=data.get("contractDate", ""),
                name=data.get("priceType", ""),
                type=data.get("counterpartyType", "")
            )]
        
        return cls(
            id=data.get("id", ""),
            full_name=data.get("fullName", data.get("full_name", "")),
            short_name=data.get("shortName", data.get("short_name", "")),
            bin=data.get("bin", ""),
            address=data.get("address", ""),
            phone=data.get("phone", data.get("phoneNumber", "")),
            phone_number=data.get("phoneNumber", data.get("phone", "")),
            email=data.get("email", ""),
            is_supplier=data.get("isSupplier", data.get("is_supplier", False)),
            is_customer=data.get("isCustomer", data.get("is_customer", False)),
            bank_accounts=bank_accounts,
            contracts=contracts,

            gov_entity=data.get("govEntity", False),
            vat_cert_date=data.get("vatCertDate", ""),
            kbe=data.get("kbe", ""),
            vat_cert_no=data.get("vatCertNo", ""),
            rnn=data.get("rnn", ""),
            vat_series=data.get("vatSeries", ""),
            residency_country=data.get("residencyCountry", ""),
            counterparty_type=data.get("counterpartyType", ""),
            account_number=data.get("accountNumber", ""),
            bic=data.get("bic", ""),
            contract_number=data.get("contractNumber", ""),
            contract_date=data.get("contractDate", ""),
            currency=data.get("currency", ""),
            price_type=data.get("priceType", "")
        )


@dataclass
class ConfirmResponse:
    success: bool
    confirmed: int
    failed: int
    errors: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "ConfirmResponse":
        return cls(
            success=data.get("success", False),
            confirmed=data.get("confirmed", 0),
            failed=data.get("failed", 0),
            errors=data.get("errors", [])
        )
