from tests.conftest import verify_practitioner


def clinical(actor):
    return {
        p for p in actor.get("/api/v1/me/access").json()["permissions"] if p.startswith("clinical")
    }


def test_clinical_permissions_require_verified_registration(owner, add_member):
    doctor = add_member(owner, "practitioner")
    assert clinical(doctor) == set()
    verify_practitioner(owner, doctor)
    assert clinical(doctor) == {"clinical.read", "clinical.write", "clinical.sign"}


def test_expired_licence_removes_clinical_permissions(owner, add_member):
    doctor = add_member(owner, "practitioner")
    verify_practitioner(owner, doctor)
    owner.put(
        f"/api/v1/members/{doctor.membership_id}/profile",
        json={
            "profession": "medical_practitioner",
            "registration_body": "HPCNA",
            "professional_number": "MP1",
            "licence_expiry_date": "2020-01-01",
        },
    )
    assert clinical(doctor) == set()


def test_changing_registration_details_resets_verification(owner, add_member):
    doctor = add_member(owner, "practitioner")
    verify_practitioner(owner, doctor)
    profile = owner.get(f"/api/v1/members/{doctor.membership_id}/profile").json()
    assert profile["registration_status"] == "verified"
    updated = owner.put(
        f"/api/v1/members/{doctor.membership_id}/profile",
        json={
            **{
                k: profile[k]
                for k in ("profession", "specialty", "registration_body", "licence_expiry_date")
            },
            "professional_number": "CHANGED",
        },
    ).json()
    assert updated["registration_status"] == "unverified"
    assert clinical(doctor) == set()
    # Changing only the specialty keeps the verification.
    verify_practitioner(owner, doctor)
    profile = owner.get(f"/api/v1/members/{doctor.membership_id}/profile").json()
    kept = owner.put(
        f"/api/v1/members/{doctor.membership_id}/profile",
        json={
            **{
                k: profile[k]
                for k in (
                    "profession",
                    "registration_body",
                    "professional_number",
                    "licence_expiry_date",
                )
            },
            "specialty": "Family medicine",
        },
    ).json()
    assert kept["registration_status"] == "verified"


def test_cannot_verify_self_or_without_details(owner, add_member):
    own = owner.get("/api/v1/me/access").json()["membership_id"]
    owner.put(
        f"/api/v1/members/{own}/profile",
        json={
            "profession": "medical_practitioner",
            "registration_body": "HPCNA",
            "professional_number": "MP9",
            "licence_expiry_date": "2099-01-01",
        },
    )
    response = owner.post(
        f"/api/v1/members/{own}/profile/verify", json={"decision": "verified", "note": "self"}
    )
    assert response.status_code == 403
    nurse = add_member(owner, "nurse")
    owner.put(f"/api/v1/members/{nurse.membership_id}/profile", json={"profession": "nurse"})
    response = owner.post(
        f"/api/v1/members/{nurse.membership_id}/profile/verify",
        json={"decision": "verified", "note": "no number"},
    )
    assert response.status_code == 422


def test_only_authorised_can_verify(owner, add_member):
    doctor = add_member(owner, "practitioner")
    receptionist = add_member(owner, "receptionist")
    owner.put(
        f"/api/v1/members/{doctor.membership_id}/profile",
        json={
            "profession": "medical_practitioner",
            "registration_body": "HPCNA",
            "professional_number": "MP2",
            "licence_expiry_date": "2099-01-01",
        },
    )
    response = receptionist.post(
        f"/api/v1/members/{doctor.membership_id}/profile/verify",
        json={"decision": "verified", "note": "trust me"},
    )
    assert response.status_code == 403


def test_provider_requires_verified_credentials(owner, add_member):
    doctor = add_member(owner, "practitioner")
    owner.put(
        f"/api/v1/members/{doctor.membership_id}/profile",
        json={
            "profession": "medical_practitioner",
            "registration_body": "HPCNA",
            "professional_number": "MP3",
            "licence_expiry_date": "2099-01-01",
        },
    )
    response = owner.post("/api/v1/providers", json={"membership_id": doctor.membership_id})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "credentials_not_verified"
    receptionist = add_member(owner, "receptionist")
    owner.put(
        f"/api/v1/members/{receptionist.membership_id}/profile",
        json={"profession": "administrative"},
    )
    response = owner.post("/api/v1/providers", json={"membership_id": receptionist.membership_id})
    assert response.status_code == 422
