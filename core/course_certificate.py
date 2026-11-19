"""Digitally signed PDF & JSON credential generator and email dispatcher for course completions."""
import base64
import datetime
import hashlib
import html as html_lib
import json
import os
import re
import secrets
import subprocess
import tempfile
import threading
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

_CERT_LOCK = threading.RLock()
_CERT_ID_RE = re.compile(r'^CERT-[A-Z0-9]{8,24}$')
_SIG_HEX_CAP = 8192


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def certs_root() -> str:
    path = os.path.join(_repo_root(), 'data', 'course_certs')
    os.makedirs(path, exist_ok=True)
    return path


def issued_dir(cert_id: str) -> str:
    if not isinstance(cert_id, str) or not _CERT_ID_RE.match(cert_id):
        raise ValueError('Invalid certificate identifier')
    target = os.path.join(certs_root(), 'issued', cert_id)
    os.makedirs(target, exist_ok=True)
    return target


def _ensure_signing_identity() -> tuple:
    root = certs_root()
    key_path = os.path.join(root, 'siraugga_signing_key.pem')
    cert_path = os.path.join(root, 'siraugga_signing_cert.pem')
    with _CERT_LOCK:
        if os.path.isfile(key_path) and os.path.isfile(cert_path):
            with open(key_path, 'rb') as kf:
                private_key = serialization.load_pem_private_key(kf.read(), password=None)
            with open(cert_path, 'rb') as cf:
                cert_pem = cf.read()
                cert = x509.load_pem_x509_certificate(cert_pem)
            return private_key, cert, cert_pem

        private_key = ec.generate_private_key(ec.SECP256R1())
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, 'Siraugga Course Certification Authority'),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Siraugga / DevCore Academy'),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, 'Verifiable Course Credentials'),
        ])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=True,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(private_key, hashes.SHA256())
        )
        key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        with open(key_path, 'wb') as kf:
            kf.write(key_pem)
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
        with open(cert_path, 'wb') as cf:
            cf.write(cert_pem)
        return private_key, cert, cert_pem


def _pdf_escape(text: str) -> str:
    clean = str(text or '').replace('\r', ' ').replace('\n', ' ')
    return clean.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def build_signed_certificate_pdf(cert_meta: dict) -> bytes:
    """Build a styled 1-page PDF 1.7 certificate with an embedded PKCS#7 /ByteRange signature."""
    private_key, cert, _ = _ensure_signing_identity()
    fp_sha256 = cert.fingerprint(hashes.SHA256()).hex()

    ops = [
        '0.06 0.09 0.16 rg 0 0 612 792 re f',
        '0.18 0.83 0.75 RG 2 w 28 28 556 736 re S',
        '0.38 0.45 0.55 RG 0.75 w 38 38 536 716 re S',
        'BT',
        '0.18 0.83 0.75 rg /F2 11 Tf 64 712 Td (' + _pdf_escape(str(cert_meta.get('academy_label') or 'SIRAUGGA  |  PRACTICAL LEARNING ACADEMY')) + ') Tj',
        '0.95 0.97 0.99 rg /F2 26 Tf 0 -42 Td (CERTIFICATE OF COMPLETION) Tj',
        '0.64 0.70 0.78 rg /F1 12 Tf 0 -30 Td (This digitally signed credential certifies that) Tj',
        '0.22 0.88 0.80 rg /F2 22 Tf 0 -32 Td (' + _pdf_escape(cert_meta.get('full_name', 'Learner')) + ') Tj',
        '0.78 0.84 0.90 rg /F1 11 Tf 0 -22 Td (Registered Email: ' + _pdf_escape(cert_meta.get('email', '')) + ') Tj',
        '0.64 0.70 0.78 rg /F1 12 Tf 0 -34 Td (has successfully completed all modules, hands-on labs, and verification checks for) Tj',
        '0.95 0.97 0.99 rg /F2 15 Tf 0 -26 Td (' + _pdf_escape(cert_meta.get('course_title', 'Siraugga Practical Course')) + ') Tj',
        '0.78 0.84 0.90 rg /F1 11 Tf 0 -34 Td (Organization / Project: ' + _pdf_escape(cert_meta.get('organization', '')) + ') Tj',
        '0 -18 Td (Role / Track: ' + _pdf_escape(cert_meta.get('role', 'Course Participant')) + ') Tj',
        '0 -18 Td (Verified Sections Completed: ' + _pdf_escape(f"{cert_meta.get('completed_sections', 0)} / {cert_meta.get('total_sections', 0)}") + ') Tj',
        '0 -18 Td (Issued Timestamp (UTC): ' + _pdf_escape(cert_meta.get('issued_at', '')) + ') Tj',
        '0 -18 Td (Certificate ID: ' + _pdf_escape(cert_meta.get('certificate_id', '')) + ') Tj',
        '0 -26 Td (Evidence Manifest SHA-256:) Tj',
        '0.58 0.90 0.82 rg /F3 8.5 Tf 0 -14 Td (' + _pdf_escape(cert_meta.get('manifest_sha256', '')) + ') Tj',
        '0.78 0.84 0.90 rg /F1 10 Tf 0 -28 Td (Digital Signature Authority: Siraugga Course Certification Authority (ECDSA P-256 / PKCS#7)) Tj',
        '0 -15 Td (Signer X.509 Fingerprint (SHA-256):) Tj',
        '0.58 0.90 0.82 rg /F3 8.5 Tf 0 -13 Td (' + _pdf_escape(fp_sha256) + ') Tj',
        'ET',
    ]
    stream_bytes = ('\n'.join(ops)).encode('latin-1', 'replace')

    placeholder_contents = '<' + ('0' * _SIG_HEX_CAP) + '>'
    placeholder_br = '[0 0000000000 0000000000 0000000000]'

    objs = [
        b'1 0 obj\n<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [7 0 R] /SigFlags 3 >> >>\nendobj\n',
        b'2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n',
        (
            b'3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
            b'/Resources << /Font << /F1 4 0 R /F2 5 0 R /F3 6 0 R >> >> '
            b'/Contents 8 0 R /Annots [7 0 R] >>\nendobj\n'
        ),
        b'4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n',
        b'5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>\nendobj\n',
        b'6 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>\nendobj\n',
        b'7 0 obj\n<< /Type /Annot /Subtype /Widget /FT /Sig /Rect [0 0 0 0] /T (SirauggaSignature1) /F 4 /P 3 0 R /V 9 0 R >>\nendobj\n',
        f'8 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n'.encode('ascii') + stream_bytes + b'\nendstream\nendobj\n',
        (
            f'9 0 obj\n<< /Type /Sig /Filter /Adobe.PPKLite /SubFilter /adbe.pkcs7.detached '
            f'/Name (Siraugga Course Certification Authority) '
            f'/Reason (Verified Completion Certificate {cert_meta.get("certificate_id", "")}) '
            f'/ByteRange {placeholder_br} /Contents {placeholder_contents} >>\nendobj\n'
        ).encode('ascii'),
    ]

    buf = bytearray(b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n')
    offsets = [0]
    for obj in objs:
        offsets.append(len(buf))
        buf.extend(obj)
    xref_pos = len(buf)
    buf.extend(f'xref\n0 {len(objs) + 1}\n0000000000 65535 f \n'.encode('ascii'))
    for off in offsets[1:]:
        buf.extend(f'{off:010d} 00000 n \n'.encode('ascii'))
    buf.extend(f'trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n'.encode('ascii'))

    raw = bytes(buf)
    c_start = raw.index(placeholder_contents.encode('ascii'))
    c_end = c_start + len(placeholder_contents)
    br_str = f'[0 {c_start:010d} {c_end:010d} {len(raw) - c_end:010d}]'
    raw = raw.replace(placeholder_br.encode('ascii'), br_str.encode('ascii'), 1)

    signed_bytes = raw[:c_start] + raw[c_end:]
    der = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(signed_bytes)
        .add_signer(cert, private_key, hashes.SHA256())
        .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.DetachedSignature])
    )
    hex_sig = der.hex()
    if len(hex_sig) > _SIG_HEX_CAP:
        raise ValueError('PKCS#7 signature exceeded reserved PDF /Contents buffer')
    padded_hex = hex_sig + ('0' * (_SIG_HEX_CAP - len(hex_sig)))
    return raw[:c_start] + b'<' + padded_hex.encode('ascii') + b'>' + raw[c_end:]


def _der_outer_length(der_bytes: bytes) -> int:
    if len(der_bytes) < 2 or der_bytes[0] != 0x30:
        return len(der_bytes)
    first_len = der_bytes[1]
    if first_len < 0x80:
        return 2 + first_len
    num_octets = first_len & 0x7F
    if num_octets == 0 or 2 + num_octets > len(der_bytes):
        return len(der_bytes)
    body_len = int.from_bytes(der_bytes[2:2 + num_octets], 'big')
    return 2 + num_octets + body_len


def verify_pdf_pkcs7_signature(pdf_bytes: bytes) -> dict:
    _, _, cert_pem = _ensure_signing_identity()
    m = re.search(rb'/ByteRange \[(\d+) (\d+) (\d+) (\d+)\]', pdf_bytes or b'')
    if not m:
        return {'valid': False, 'reason': 'Missing PDF /ByteRange'}
    b0, l0, b1, l1 = [int(x) for x in m.groups()]
    if b0 != 0 or l0 <= 0 or b1 <= l0 or (b1 + l1) > len(pdf_bytes):
        return {'valid': False, 'reason': 'Invalid PDF /ByteRange offsets'}
    contents_slice = pdf_bytes[b0 + l0:b1]
    if not (contents_slice.startswith(b'<') and contents_slice.endswith(b'>')):
        return {'valid': False, 'reason': 'Malformed PDF /Contents hex block'}
    der_padded = bytes.fromhex(contents_slice[1:-1].decode('ascii'))
    der_sig = der_padded[:_der_outer_length(der_padded)]
    signed_data = pdf_bytes[b0:b0 + l0] + pdf_bytes[b1:b1 + l1]

    with tempfile.TemporaryDirectory() as td:
        cert_f = os.path.join(td, 'cert.pem')
        data_f = os.path.join(td, 'data.bin')
        sig_f = os.path.join(td, 'sig.der')
        with open(cert_f, 'wb') as f:
            f.write(cert_pem)
        with open(data_f, 'wb') as f:
            f.write(signed_data)
        with open(sig_f, 'wb') as f:
            f.write(der_sig)
        proc = subprocess.run(
            [
                'openssl', 'cms', '-verify',
                '-inform', 'DER',
                '-in', sig_f,
                '-content', data_f,
                '-CAfile', cert_f,
                '-purpose', 'any',
                '-out', os.devnull,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return {
            'valid': proc.returncode == 0,
            'byte_range': [b0, l0, b1, l1],
            'cms_bytes': len(der_sig),
            'reason': 'CMS Verification successful' if proc.returncode == 0 else (proc.stderr or 'Verification failed').strip(),
        }


def build_signed_credential(cert_meta: dict, pdf_bytes: bytes) -> dict:
    private_key, cert, cert_pem = _ensure_signing_identity()
    fp_sha256 = cert.fingerprint(hashes.SHA256()).hex()
    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()

    payload = {
        'schema': 'siraugga.course.certificate.v1',
        'certificate_id': cert_meta['certificate_id'],
        'issuer': 'Siraugga Course Certification Authority',
        'signer_fingerprint_sha256': fp_sha256,
        'subject': {
            'full_name': cert_meta['full_name'],
            'email': cert_meta['email'],
            'organization': cert_meta.get('organization', ''),
            'role': cert_meta.get('role', 'Course Participant'),
        },
        'course': {
            'course_id': cert_meta['course_id'],
            'course_title': cert_meta['course_title'],
            'completed_sections': cert_meta['completed_sections'],
            'total_sections': cert_meta['total_sections'],
            'manifest_sha256': cert_meta.get('manifest_sha256', ''),
        },
        'issued_at': cert_meta['issued_at'],
        'pdf_sha256': pdf_sha256,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    sig_der = private_key.sign(canonical, ec.ECDSA(hashes.SHA256()))
    return {
        'payload': payload,
        'signature_algorithm': 'ECDSA-P256-SHA256',
        'signature_b64': base64.b64encode(sig_der).decode('ascii'),
        'signer_cert_pem': cert_pem.decode('utf-8'),
    }


def verify_credential_payload(envelope: dict) -> dict:
    try:
        payload = envelope['payload']
        sig_der = base64.b64decode(envelope['signature_b64'])
        cert_pem = envelope['signer_cert_pem'].encode('utf-8')
        _, authority_cert, _ = _ensure_signing_identity()
        embedded_cert = x509.load_pem_x509_certificate(cert_pem)
        fp_match = embedded_cert.fingerprint(hashes.SHA256()) == authority_cert.fingerprint(hashes.SHA256())
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
        authority_cert.public_key().verify(sig_der, canonical, ec.ECDSA(hashes.SHA256()))
        return {'valid': bool(fp_match), 'reason': 'Signature verified' if fp_match else 'Signer certificate mismatch'}
    except Exception as exc:
        return {'valid': False, 'reason': str(exc)}


def _build_certificate_email_bodies(cert_meta: dict, envelope: dict) -> tuple:
    payload = envelope['payload']
    fp = payload['signer_fingerprint_sha256']
    body_html = (
        f"<p>Congratulations <strong>{html_lib.escape(cert_meta['full_name'])}</strong>,</p>"
        f"<p>You have completed all required modules, hands-on labs, reflections, and the end-of-course survey for "
        f"<strong>{html_lib.escape(cert_meta['course_title'])}</strong>.</p>"
        "<p>Your digitally signed certificate PDF and standalone cryptographic verification credential are attached to this email.</p>"
        '<table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:13px;">'
        f"<tr><td style=\"padding:6px 0;color:#9aa4b2;\">Certificate ID</td><td style=\"padding:6px 0;color:#ffffff;font-family:monospace;\">{html_lib.escape(cert_meta['certificate_id'])}</td></tr>"
        f"<tr><td style=\"padding:6px 0;color:#9aa4b2;\">Recipient</td><td style=\"padding:6px 0;color:#ffffff;\">{html_lib.escape(cert_meta['full_name'])} ({html_lib.escape(cert_meta['email'])})</td></tr>"
        f"<tr><td style=\"padding:6px 0;color:#9aa4b2;\">Organization</td><td style=\"padding:6px 0;color:#ffffff;\">{html_lib.escape(cert_meta.get('organization', ''))}</td></tr>"
        f"<tr><td style=\"padding:6px 0;color:#9aa4b2;\">Issued (UTC)</td><td style=\"padding:6px 0;color:#ffffff;font-family:monospace;\">{html_lib.escape(cert_meta['issued_at'])}</td></tr>"
        f"<tr><td style=\"padding:6px 0;color:#9aa4b2;\">Signature Algorithm</td><td style=\"padding:6px 0;color:#2dd4bf;font-family:monospace;\">ECDSA-P256-SHA256 + PDF PKCS#7</td></tr>"
        f"<tr><td style=\"padding:6px 0;color:#9aa4b2;\">PDF SHA-256</td><td style=\"padding:6px 0;color:#ffffff;font-family:monospace;word-break:break-all;\">{payload['pdf_sha256']}</td></tr>"
        f"<tr><td style=\"padding:6px 0;color:#9aa4b2;\">Authority Fingerprint</td><td style=\"padding:6px 0;color:#ffffff;font-family:monospace;word-break:break-all;\">{fp}</td></tr>"
        "</table>"
    )
    from services.mail import engine as mail_eng
    full_html = mail_eng.build_email_template(
        title='Your Digitally Signed Course Certificate of Completion',
        body_html=body_html,
    )
    text_body = (
        f"Congratulations {cert_meta['full_name']},\n\n"
        f"You have completed {cert_meta['course_title']}.\n"
        f"Certificate ID: {cert_meta['certificate_id']}\n"
        f"Issued (UTC): {cert_meta['issued_at']}\n"
        f"PDF SHA-256: {payload['pdf_sha256']}\n"
        f"Authority Fingerprint (SHA-256): {fp}\n"
        f"Signature Algorithm: ECDSA-P256-SHA256 + PDF PKCS#7\n\n"
        "Attached: digitally signed Certificate PDF and JSON signature credential.\n"
    )
    return full_html, text_body


def email_signed_certificate(cert_meta: dict, pdf_bytes: bytes, cred_bytes: bytes, envelope: dict, force_local: bool = False) -> dict:
    from services.mail import config as mail_cfg_mod
    from services.mail import engine as mail_eng

    to_addr = cert_meta['email']
    cert_id = cert_meta['certificate_id']
    subject = f"Digitally Signed Certificate of Completion — {cert_meta['course_title']} ({cert_id})"
    html_body, text_body = _build_certificate_email_bodies(cert_meta, envelope)

    pdf_name = f"Certificate_of_Completion_{cert_id}.pdf"
    sig_name = f"Certificate_Verification_{cert_id}.sig.json"
    attachments_meta = [
        {'filename': pdf_name, 'content_type': 'application/pdf', 'size': len(pdf_bytes), 'sha256': hashlib.sha256(pdf_bytes).hexdigest()},
        {'filename': sig_name, 'content_type': 'application/json', 'size': len(cred_bytes), 'sha256': hashlib.sha256(cred_bytes).hexdigest()},
    ]

    backend = (mail_cfg_mod.config.MAIL_BACKEND or 'local').lower()
    dry_run = force_local or os.environ.get('DEVCORE_MAIL_DRY_RUN', '') == '1'
    sender = mail_cfg_mod.config.MAIL_DEFAULT_SENDER or 'devcore.fammaly@gmail.com'

    record = {
        'id': cert_id,
        'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'to': to_addr,
        'from': sender,
        'subject': subject,
        'text': text_body,
        'html': html_body,
        'attachments': attachments_meta,
        'backend': 'local' if dry_run else backend,
        'status': 'QUEUED',
    }

    if dry_run or backend == 'local':
        record['status'] = 'DELIVERED_LOCAL'
        record['details'] = 'Captured with signed certificate attachments in unified local mailbox.'
        mail_eng._append_to_local_mailbox(record)
        return {'ok': True, 'status': record['status'], 'message': f'Certificate queued/captured locally for {to_addr}.', 'recipient': to_addr, 'attachments': attachments_meta}

    if backend == 'smtp':
        username, password = mail_eng._smtp_credentials()
        if not username or not password:
            mail_eng._record_failure(record, mail_eng.SMTP_MISSING_CREDENTIALS_ERROR)
            return {'ok': False, 'status': 'FAILED', 'message': mail_eng.SMTP_MISSING_CREDENTIALS_ERROR, 'recipient': to_addr, 'attachments': attachments_meta}
        if not sender or 'eprofile.local' in sender:
            sender = username
            record['from'] = sender

        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = to_addr
        msg['X-Siraugga-Certificate-ID'] = cert_id

        alt = MIMEMultipart('alternative')
        alt.attach(MIMEText(text_body, 'plain', 'utf-8'))
        alt.attach(MIMEText(html_body, 'html', 'utf-8'))
        msg.attach(alt)

        pdf_part = MIMEApplication(pdf_bytes, _subtype='pdf')
        pdf_part.add_header('Content-Disposition', 'attachment', filename=pdf_name)
        msg.attach(pdf_part)

        sig_part = MIMEApplication(cred_bytes, _subtype='json')
        sig_part.add_header('Content-Disposition', 'attachment', filename=sig_name)
        msg.attach(sig_part)

        try:
            server = mail_eng._open_smtp_connection(username, password)
            try:
                server.sendmail(sender, [to_addr], msg.as_string())
            finally:
                try:
                    server.quit()
                except Exception:
                    server.close()
        except Exception as exc:
            mail_eng._record_failure(record, f'SMTP Certificate Delivery Failed: {exc}')
            return {'ok': False, 'status': 'FAILED', 'message': f'SMTP Certificate Delivery Failed: {exc}', 'recipient': to_addr, 'attachments': attachments_meta}

        record['status'] = 'SENT_SMTP'
        record['details'] = f'Transmitted signed certificate via {mail_cfg_mod.config.MAIL_SERVER}'
        mail_eng._append_to_local_mailbox(record)
        return {'ok': True, 'status': 'SENT_SMTP', 'message': f'Digitally signed certificate emailed to {to_addr}.', 'recipient': to_addr, 'attachments': attachments_meta}

    record['status'] = 'DELIVERED_LOCAL'
    mail_eng._append_to_local_mailbox(record)
    return {'ok': True, 'status': 'DELIVERED_LOCAL', 'message': f'Certificate captured locally for {to_addr}.', 'recipient': to_addr, 'attachments': attachments_meta}


def issue_and_email_certificate(
    course_id: str,
    course_title: str,
    registration: dict,
    completed_sections: int,
    total_sections: int,
    manifest_sha256: str,
    sandbox_dir: str = None,
    learner_handle: str = 'learner',
    force_local_mail: bool = False,
) -> dict:
    cert_id = 'CERT-' + secrets.token_hex(6).upper()
    issued_at = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    cert_meta = {
        'certificate_id': cert_id,
        'course_id': course_id,
        'course_title': course_title,
        'full_name': str(registration.get('full_name') or 'Course Learner').strip(),
        'email': str(registration.get('email') or '').strip(),
        'organization': str(registration.get('organization') or 'Independent Learner').strip(),
        'role': str(registration.get('role') or 'Course Participant').strip(),
        'completed_sections': int(completed_sections),
        'total_sections': int(total_sections),
        'manifest_sha256': str(manifest_sha256 or ''),
        'issued_at': issued_at,
    }

    pdf_bytes = build_signed_certificate_pdf(cert_meta)
    envelope = build_signed_credential(cert_meta, pdf_bytes)
    cred_bytes = json.dumps(envelope, indent=2, ensure_ascii=False).encode('utf-8')

    target_dir = issued_dir(cert_id)
    pdf_path = os.path.join(target_dir, f'Certificate_of_Completion_{cert_id}.pdf')
    sig_path = os.path.join(target_dir, f'Certificate_Verification_{cert_id}.sig.json')
    with open(pdf_path, 'wb') as pf:
        pf.write(pdf_bytes)
    with open(sig_path, 'wb') as sf:
        sf.write(cred_bytes)

    if sandbox_dir and os.path.isdir(sandbox_dir):
        ev_dir = os.path.join(sandbox_dir, 'evidence', re.sub(r'[^a-z0-9_-]', '', (learner_handle or 'learner').lower()) or 'learner')
        os.makedirs(ev_dir, exist_ok=True)
        try:
            with open(os.path.join(ev_dir, f'Certificate_of_Completion_{cert_id}.pdf'), 'wb') as epf:
                epf.write(pdf_bytes)
            with open(os.path.join(ev_dir, f'Certificate_Verification_{cert_id}.sig.json'), 'wb') as esf:
                esf.write(cred_bytes)
        except Exception:
            pass

    email_res = email_signed_certificate(cert_meta, pdf_bytes, cred_bytes, envelope, force_local=force_local_mail)
    payload = envelope['payload']
    return {
        'certificate': {
            'certificate_id': cert_id,
            'full_name': cert_meta['full_name'],
            'email': cert_meta['email'],
            'organization': cert_meta['organization'],
            'role': cert_meta['role'],
            'course_id': course_id,
            'course_title': course_title,
            'issued_at': issued_at,
            'pdf_sha256': payload['pdf_sha256'],
            'manifest_sha256': cert_meta['manifest_sha256'],
            'signer_fingerprint_sha256': payload['signer_fingerprint_sha256'],
            'signature_algorithm': envelope['signature_algorithm'],
            'download_url': f'/api/course/certificate/download?cert_id={cert_id}',
            'verify_url': f'/api/course/certificate/verify?cert_id={cert_id}',
            'email_status': email_res.get('status', ''),
            'email_ok': bool(email_res.get('ok')),
            'email_message': email_res.get('message', ''),
        },
        'email_delivery': email_res,
    }


def load_issued_certificate(cert_id: str) -> tuple:
    target_dir = issued_dir(cert_id)
    pdf_path = os.path.join(target_dir, f'Certificate_of_Completion_{cert_id}.pdf')
    sig_path = os.path.join(target_dir, f'Certificate_Verification_{cert_id}.sig.json')
    if not os.path.isfile(pdf_path) or not os.path.isfile(sig_path):
        return None, None
    with open(pdf_path, 'rb') as pf:
        pdf_bytes = pf.read()
    with open(sig_path, 'r', encoding='utf-8') as sf:
        envelope = json.load(sf)
    return pdf_bytes, envelope
