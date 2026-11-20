
import os
from collections import defaultdict

from google.oauth2 import service_account
from googleapiclient.discovery import build
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Document


SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def get_drive_service():
    credentials_path = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]

    credentials = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=SCOPES,
    )

    return build(
        "drive",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )


def get_drive_files(service, folder_id):
    files_by_name = defaultdict(list)
    page_token = None

    while True:
        response = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType)",
            pageSize=1000,
            pageToken=page_token,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
        ).execute()

        for file in response.get("files", []):
            if file["mimeType"] == "application/vnd.google-apps.folder":
                continue

            files_by_name[file["name"]].append(file["id"])

        page_token = response.get("nextPageToken")

        if not page_token:
            break

    return files_by_name


def main():
    database_url = os.environ["DATABASE_URL"]
    folder_id = os.environ["GOOGLE_DRIVE_FOLDER_ID"]

    service = get_drive_service()
    drive_files = get_drive_files(service, folder_id)

    engine = create_engine(database_url, pool_pre_ping=True)

    try:
        with Session(engine) as session:
            documents = session.execute(
                select(Document).order_by(Document.id)
            ).scalars().all()

            matches = []
            unmatched = []
            ambiguous = []
            already_linked = []

            for document in documents:
                filename = document.original_filename

                if document.drive_file_id:
                    already_linked.append(filename)
                    continue

                candidates = drive_files.get(filename, [])

                if len(candidates) == 1:
                    matches.append((document, candidates[0]))

                elif len(candidates) > 1:
                    ambiguous.append(filename)

                else:
                    unmatched.append(filename)

            print("\nGoogle Drive synchronization preview")
            print("-------------------------------------")

            for document, file_id in matches:
                print(
                    f"MATCH: {document.original_filename} "
                    f"-> {file_id}"
                )

            print(f"\nReady to link: {len(matches)}")
            print(f"Already linked: {len(already_linked)}")
            print(f"No exact filename match: {len(unmatched)}")
            print(f"Duplicate filenames in Drive: {len(ambiguous)}")

            if unmatched:
                print("\nUnmatched database documents:")
                for filename in unmatched:
                    print(f"  - {filename}")

            if ambiguous:
                print("\nAmbiguous Drive filenames (skipped):")
                for filename in ambiguous:
                    print(f"  - {filename}")

            if not matches:
                print("\nNothing to update.")
                return

            confirmation = input(
                '\nType exactly "LINK DRIVE FILES" to continue: '
            ).strip()

            if confirmation != "LINK DRIVE FILES":
                print("Cancelled. No database changes were made.")
                return

            # Check that no Drive ID is already assigned to another record.
            ids_to_link = [file_id for _, file_id in matches]

            existing_ids = set(
                session.execute(
                    select(Document.drive_file_id).where(
                        Document.drive_file_id.in_(ids_to_link)
                    )
                ).scalars().all()
            )

            if existing_ids:
                raise RuntimeError(
                    "One or more Drive files are already linked "
                    "to another document. No changes committed."
                )

            for document, file_id in matches:
                document.drive_file_id = file_id

            session.commit()

            print(
                f"\nSuccessfully linked {len(matches)} "
                "Google Drive files."
            )

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
