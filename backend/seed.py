"""Demo/dev data seeder for an electric utility co-op.

Run as:  .venv/bin/python -m backend.seed

Idempotent guard: if any Integration rows exist, prints a message and exits
without changes. Otherwise seeds users, lookups, ~10 integrations, and a
small link graph (including one cycle and one integrated pair).
"""
from datetime import date

from sqlalchemy import select

from . import audit, search
from .database import SessionLocal, engine
from .models import (
    AppUser,
    AuditAction,
    Base,
    CredentialType,
    Integration,
    IntegrationComment,
    IntegrationLink,
    IntegrationType,
    Level,
    LinkKind,
    Role,
    Status,
    System,
    Tag,
)


def _flow(a: Integration, b: Integration) -> IntegrationLink:
    """Data flows a -> b."""
    return IntegrationLink(source_id=a.id, target_id=b.id, kind=LinkKind.flow)


def _integrated(a: Integration, b: Integration) -> IntegrationLink:
    """Undirected edge, canonicalized so source_id < target_id."""
    source_id, target_id = sorted([a.id, b.id])
    return IntegrationLink(source_id=source_id, target_id=target_id, kind=LinkKind.integrated)


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.scalar(select(Integration.id).limit(1)) is not None:
            print("Integrations already exist; skipping seed (no changes made).")
            return

        # --- users ----------------------------------------------------------
        ana = AppUser(email="ana.admin@example.com", display_name="Ana Admin", role=Role.integration)
        greg = AppUser(email="greg.lineman@example.com", display_name="Greg Lineman", role=Role.general)
        priya = AppUser(email="priya.analyst@example.com", display_name="Priya Analyst", role=Role.general)
        users = [ana, greg, priya]
        db.add_all(users)

        # --- lookups ----------------------------------------------------------
        tag_names = ["billing", "outage", "scada", "member-portal", "finance", "compliance"]
        tags = {n: Tag(name=n) for n in tag_names}
        system_names = [
            "SAP", "Salesforce", "NetSuite", "Workday",
            "S3 Landing", "Kafka", "Data Lake", "ServiceNow",
        ]
        systems = {n: System(name=n) for n in system_names}
        types = {n: IntegrationType(name=n) for n in ["REST", "SOAP", "File", "bespoke"]}
        creds = {n: CredentialType(name=n) for n in ["OAuth2", "Basic", "API Key", "Certificate"]}
        db.add_all([*tags.values(), *systems.values(), *types.values(), *creds.values()])
        db.flush()

        # --- integrations ----------------------------------------------------
        billing_sync = Integration(
            name="Member Billing Sync",
            description=(
                "Nightly sync of member billing determinants from SAP IS-U to "
                "NetSuite for general-ledger posting and rate reconciliation."
            ),
            status=Status.prod,
            type=types["REST"],
            credential_type=creds["OAuth2"],
            complexity=Level.high,
            business_logic=Level.high,
            tags=[tags["billing"], tags["finance"]],
            sources=[systems["SAP"]],
            targets=[systems["NetSuite"]],
            associated_projects="CIS Modernization",
            documentation_url="https://wiki.example.com/integrations/member-billing-sync",
            account_used="svc-billing-sync",
            needed_roles="NetSuite GL Writer; SAP IS-U Read",
            design_approved=True,
            design_approver=ana,
            design_approval_date=date(2026, 1, 20),
            code_approved=True,
            code_approver=ana,
            code_approval_date=date(2026, 2, 14),
            created_by=ana,
            updated_by=ana,
        )
        outage_stream = Integration(
            name="Outage Event Stream",
            description=(
                "Publishes outage and restoration events from the outage "
                "management system to Kafka for downstream notification and "
                "analytics consumers."
            ),
            status=Status.prod,
            type=types["bespoke"],
            credential_type=creds["Certificate"],
            complexity=Level.medium,
            business_logic=Level.medium,
            tags=[tags["outage"], tags["scada"]],
            sources=[systems["ServiceNow"]],
            targets=[systems["Kafka"]],
            account_used="svc-oms-publisher",
            created_by=greg,
            updated_by=greg,
        )
        scada_ingest = Integration(
            name="SCADA Telemetry Ingest",
            description=(
                "Streams substation SCADA telemetry (voltage, load, breaker "
                "state) from the Kafka bus into the S3 landing zone and "
                "curates it into the Data Lake for engineering analytics."
            ),
            status=Status.prod,
            type=types["bespoke"],
            credential_type=creds["Certificate"],
            complexity=Level.high,
            business_logic=Level.low,
            tags=[tags["scada"]],
            sources=[systems["Kafka"]],
            targets=[systems["S3 Landing"], systems["Data Lake"]],
            design_approved=True,
            design_approver=ana,
            design_approval_date=date(2025, 11, 5),
            created_by=ana,
            updated_by=priya,
        )
        portal_feed = Integration(
            name="Member Portal Account Feed",
            description=(
                "Pushes member account, usage, and billing summary data to the "
                "member self-service portal (Salesforce Experience Cloud)."
            ),
            status=Status.qa,
            type=types["REST"],
            credential_type=creds["OAuth2"],
            complexity=Level.medium,
            business_logic=Level.medium,
            tags=[tags["member-portal"], tags["billing"]],
            sources=[systems["NetSuite"]],
            targets=[systems["Salesforce"]],
            associated_projects="Member Portal 2.0",
            created_by=priya,
            updated_by=priya,
        )
        payroll_export = Integration(
            name="Payroll Journal Export",
            description=(
                "Bi-weekly payroll journal export from Workday to NetSuite, "
                "with union wage and storm-duty overtime allocations."
            ),
            status=Status.test,
            type=types["File"],
            credential_type=creds["Basic"],
            complexity=Level.low,
            business_logic=Level.medium,
            tags=[tags["finance"]],
            sources=[systems["Workday"]],
            targets=[systems["NetSuite"]],
            account_used="svc-payroll-sftp",
            created_by=greg,
            updated_by=ana,
        )
        service_orders = Integration(
            name="Service Order Dispatch",
            description=(
                "Creates and tracks field service orders in ServiceNow from "
                "member portal requests (connects, disconnects, tree trimming)."
            ),
            status=Status.dev,
            type=types["SOAP"],
            credential_type=creds["Basic"],
            complexity=Level.medium,
            business_logic=Level.high,
            tags=[tags["member-portal"]],
            sources=[systems["Salesforce"]],
            targets=[systems["ServiceNow"]],
            created_by=priya,
            updated_by=greg,
        )
        meter_loader = Integration(
            name="AMI Meter Reading Loader",
            description=(
                "Loads AMI meter interval reading files from the headend drop "
                "zone into the Data Lake and SAP billing staging tables."
            ),
            status=Status.prod,
            type=types["File"],
            credential_type=creds["API Key"],
            complexity=Level.medium,
            business_logic=Level.low,
            tags=[tags["billing"], tags["scada"]],
            sources=[systems["S3 Landing"]],
            targets=[systems["Data Lake"], systems["SAP"]],
            account_used="svc-ami-loader",
            created_by=greg,
            updated_by=greg,
        )
        outage_notifier = Integration(
            name="Outage Notification Dispatcher",
            description=(
                "Sends outage and estimated-restoration notifications (SMS and "
                "email) to affected members based on outage events."
            ),
            status=Status.fixing,
            type=types["REST"],
            credential_type=creds["OAuth2"],
            complexity=Level.medium,
            business_logic=Level.high,
            tags=[tags["outage"], tags["member-portal"]],
            sources=[systems["Kafka"]],
            targets=[systems["Salesforce"]],
            notes="Retry storm during the May wind event duplicated texts; backoff fix in progress.",
            created_by=priya,
            updated_by=ana,
        )
        gis_sync = Integration(
            name="GIS Asset Sync",
            description=(
                "Synchronizes pole, transformer, and feeder asset records "
                "between the GIS extract in the Data Lake and the ServiceNow "
                "asset registry for joint-use and inspection compliance."
            ),
            status=Status.planning,
            type=types["REST"],
            credential_type=creds["API Key"],
            complexity=Level.high,
            business_logic=Level.medium,
            tags=[tags["compliance"], tags["scada"]],
            sources=[systems["Data Lake"]],
            targets=[systems["ServiceNow"]],
            created_by=ana,
            updated_by=ana,
        )
        tariff_publisher = Integration(
            name="Rate Tariff Publisher",
            description=(
                "Publishes board-approved rate tariffs and rider schedules "
                "from NetSuite to SAP billing and the member portal."
            ),
            status=Status.dev,
            type=types["REST"],
            credential_type=creds["OAuth2"],
            complexity=Level.low,
            business_logic=Level.high,
            tags=[tags["billing"], tags["compliance"]],
            sources=[systems["NetSuite"]],
            targets=[systems["SAP"], systems["Salesforce"]],
            created_by=greg,
            updated_by=priya,
        )

        integrations = [
            billing_sync, outage_stream, scada_ingest, portal_feed, payroll_export,
            service_orders, meter_loader, outage_notifier, gis_sync, tariff_publisher,
        ]
        db.add_all(integrations)
        db.flush()  # assign ids before building link edges

        # --- links: small graph with one cycle and one integrated pair --------
        links = [
            # cycle: billing -> portal feed -> tariff publisher -> billing
            _flow(billing_sync, portal_feed),
            _flow(portal_feed, tariff_publisher),
            _flow(tariff_publisher, billing_sync),
            _flow(meter_loader, billing_sync),
            _flow(scada_ingest, outage_stream),
            _flow(outage_stream, outage_notifier),
            _flow(gis_sync, outage_notifier),
            _flow(payroll_export, billing_sync),
            _integrated(service_orders, gis_sync),
        ]
        db.add_all(links)
        db.flush()

        # --- search documents (after links exist) ----------------------------
        for i in integrations:
            search.refresh_search_document(db, i)

        # --- audit trail: record each seeded row as a creation event ----------
        for i in integrations:
            audit.audit_created(
                db, i, audit.snapshot(db, i), i.created_by, audit.new_change_group_id()
            )

        # --- a couple of demo comments ----------------------------------------
        demo_comments = [
            (billing_sync, greg, "Watch the nightly window — SAP locks the AR tables until ~02:00."),
            (billing_sync, priya, "Reconciliation report lives in the Finance SharePoint, folder 'Billing/Recon'."),
            (scada_ingest, ana, "Vendor rotates the cert annually in March; renew the credential before then."),
        ]
        for integ, author, body in demo_comments:
            db.add(
                IntegrationComment(
                    integration_id=integ.id,
                    body=body,
                    author_email=author.email,
                    author_name=author.display_name,
                )
            )
            audit.write_entry(
                db,
                integration_id=integ.id,
                integration_name=integ.name,
                action=AuditAction.commented,
                user=author,
                change_group_id=audit.new_change_group_id(),
                field="comment",
                new_value=body,
            )

        db.commit()

        for i in integrations:
            print(f"  seeded: {i.name} [{i.status.value}]")
        print(
            f"Seeded {len(users)} users, {len(tags)} tags, {len(systems)} systems, "
            f"{len(types)} types, {len(creds)} credential types, "
            f"{len(integrations)} integrations, {len(links)} links."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
