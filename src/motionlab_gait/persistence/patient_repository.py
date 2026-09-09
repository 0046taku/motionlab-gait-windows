from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime

from motionlab_gait.domain.models import Patient
from motionlab_gait.persistence.database import Database


class DuplicatePatientCodeError(ValueError):
    pass


class PatientRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(
        self,
        patient_code: str,
        name: str = "",
        notes: str = "",
        *,
        affected_side: str = "none",
        diagnosis: str = "",
        onset_date: str | None = None,
        height_cm: float | None = None,
    ) -> Patient:
        code = patient_code.strip()
        display_name = name.strip()
        if not code:
            raise ValueError("患者IDを入力してください。")
        if len(code) > 64:
            raise ValueError("患者IDは64文字以内で入力してください。")
        if len(display_name) > 128:
            raise ValueError("患者名は128文字以内で入力してください。")
        if len(notes) > 2_000:
            raise ValueError("メモは2000文字以内で入力してください。")
        if affected_side not in {"left", "right", "none"}:
            raise ValueError("患側の値が不正です。")
        if height_cm is not None and not 30 <= height_cm <= 250:
            raise ValueError("身長は30〜250 cmで入力してください。")
        now = datetime.now(UTC)
        patient = Patient(
            id=str(uuid.uuid4()),
            patient_code=code,
            name=display_name,
            notes=notes.strip(),
            created_at=now,
            affected_side=affected_side,
            diagnosis=diagnosis.strip(),
            onset_date=onset_date,
            height_cm=height_cm,
            updated_at=now,
        )
        try:
            with self.database.connection() as connection:
                connection.execute(
                    """
                    INSERT INTO patients (
                        id, patient_code, name, notes, created_at, affected_side,
                        diagnosis, onset_date, height_cm, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        patient.id,
                        patient.patient_code,
                        patient.name,
                        patient.notes,
                        patient.created_at.isoformat(),
                        patient.affected_side,
                        patient.diagnosis,
                        patient.onset_date,
                        patient.height_cm,
                        patient.updated_at.isoformat() if patient.updated_at else None,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise DuplicatePatientCodeError("同じ患者IDがすでに登録されています。") from error
        return patient

    def list_all(self) -> list[Patient]:
        with self.database.connection() as connection:
            rows = connection.execute("SELECT * FROM patients ORDER BY created_at DESC").fetchall()
        return [self._from_row(row) for row in rows]

    def get(self, patient_id: str) -> Patient | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM patients WHERE id = ?", (patient_id,)
            ).fetchone()
        return None if row is None else self._from_row(row)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Patient:
        return Patient(
            id=str(row["id"]),
            patient_code=str(row["patient_code"]),
            name=str(row["name"]),
            notes=str(row["notes"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            affected_side=str(row["affected_side"]),
            diagnosis=str(row["diagnosis"]),
            onset_date=str(row["onset_date"]) if row["onset_date"] else None,
            height_cm=float(row["height_cm"]) if row["height_cm"] is not None else None,
            updated_at=(
                datetime.fromisoformat(str(row["updated_at"])) if row["updated_at"] else None
            ),
        )
