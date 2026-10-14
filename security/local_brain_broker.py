import argparse
import json
import os
import re
import subprocess
import sys

LLAMA_CLI = os.path.expanduser("~/.local/llama-cpp/llama-cli")
MODEL_PATH = os.path.expanduser("~/.local/models/qwen2.5-1.5b-instruct-q4_k_m.gguf")


_DEVCORE_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if _DEVCORE_ROOT not in sys.path:
    sys.path.insert(0, _DEVCORE_ROOT)

from security.central_logger import log_siem_event
from security.raugus_resolver import normalize_cross_platform_path
from security.swarm_telemetry import SwarmFlowLogger

_PRESIDIO_ANALYZER = None
_PRESIDIO_ANONYMIZER = None

_TEXT_EXTENSIONS = {
    ".txt", ".md", ".json", ".csv", ".yaml", ".yml",
    ".ini", ".cfg", ".rst", ".py", ".js", ".html", ".xml", ".log",
}
_SKIP_FILENAMES = {
    "desktop.ini",
    ".ds_store",
    ".849c9593-d756-4e56-8d6e-42412f2a707b",
}


def offline_scrub_pii(text: str, use_nlp: bool = False, stage: str = "stream") -> str:
    """
    Strictly offline PII, South African ID, cellphone/landline, address, medical,
    and secret scrubbing using deterministic regex + local Microsoft Presidio NLP.
    Never makes any external network/cloud calls. Logs any PII/secret redactions to SIEM.
    """
    if not text:
        return text

    # 1. Deterministic regex scrubbing for secrets, keys, emails, and IPs
    scrubbed = re.sub(r"AIza[0-9A-Za-z\-_]{35}", "<REDACTED_API_KEY>", text)
    scrubbed = re.sub(r"sk-[0-9A-Za-z]{20,}", "<REDACTED_SECRET_KEY>", scrubbed)
    scrubbed = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "<REDACTED_EMAIL>",
        scrubbed,
    )
    scrubbed = re.sub(
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        "<REDACTED_IP>",
        scrubbed,
    )
    scrubbed = re.sub(
        r"(?i)(password|passwd|secret|api_key|token)\s*[:=]\s*['\"]?[^\s,'\"\n]+['\"]?",
        r"\1: <REDACTED_SECRET>",
        scrubbed,
    )

    # 2. South African 13-Digit ID Numbers (YYMMDD SSSS C A Z) & Labeled IDs/Student/Tax Numbers
    scrubbed = re.sub(
        r"\b\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])[\s\-]?\d{4}[\s\-]?[01]\d[\s\-]?\d\b",
        "<REDACTED_SA_ID>",
        scrubbed,
    )
    scrubbed = re.sub(
        r"(?i)\b(id\s*(?:no|number|#)|passport\s*(?:no|number|#)?|student\s*(?:no|number|#)|learner\s*(?:no|number|#)|tax\s*(?:no|number|#)|sars\s*(?:no|number|#)|registration\s*(?:no|number|#))\s*[:=\-]?\s*[A-Z0-9/\-\s]{5,22}\b",
        r"\1: <REDACTED_ID_NUMBER>",
        scrubbed,
    )

    # 3. South African & International Cellphone and Landline Numbers
    scrubbed = re.sub(
        r"(?:\+27|0027)[\s\-\.]?(?:\(0\))?[\s\-\.]?[1-8]\d[\s\-\.]?\d{3}[\s\-\.]?\d{4}\b",
        "<REDACTED_PHONE>",
        scrubbed,
    )
    scrubbed = re.sub(
        r"\b(?:\(0[1-8]\d\)|0[1-8]\d)[\s\-\.]?\d{3}[\s\-\.]?\d{4}\b",
        "<REDACTED_PHONE>",
        scrubbed,
    )
    scrubbed = re.sub(
        r"\+\d{1,3}[\s\-\.]?\(?\d{1,4}\)?[\s\-\.]?\d{3,4}[\s\-\.]?\d{3,4}\b",
        "<REDACTED_PHONE>",
        scrubbed,
    )

    # 4. Financial Identifiers (Card Numbers & Bank Accounts)
    scrubbed = re.sub(
        r"\b(?:\d{4}[\s\-]){3}\d{1,4}\b",
        "<REDACTED_FINANCIAL_ID>",
        scrubbed,
    )
    scrubbed = re.sub(
        r"(?i)\b(account\s*(?:no|number|#)|acc\s*(?:no|number|#)|iban)\s*[:=\-]?\s*\d[\d\s\-]{5,18}\d\b",
        r"\1: <REDACTED_BANK_ACCOUNT>",
        scrubbed,
    )

    # 5. Physical Street Addresses & POPIA Section 26 Medical/Disability Identifiers
    scrubbed = re.sub(
        r"\b\d{1,5}\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3}\s+(?:Street|St|Road|Rd|Avenue|Ave|Drive|Dr|Lane|Ln|Boulevard|Blvd|Close|Crescent|Cres|Way|Court|Ct|Place|Pl)\b",
        "<REDACTED_ADDRESS>",
        scrubbed,
    )
    scrubbed = re.sub(
        r"(?i)\b(medical\s*aid\s*(?:no|number)?|diagnosis|disability\s*status|visual\s*acuity|chronic\s*medication|icd[\-\s]?10)\s*[:=\-]\s*[^\n,;]+",
        r"\1: <REDACTED_MEDICAL_INFO>",
        scrubbed,
    )

    # 6. Local Microsoft Presidio NLP scrubbing (100% offline spaCy engine for PERSON, LOCATION, etc.)
    if use_nlp:
        global _PRESIDIO_ANALYZER, _PRESIDIO_ANONYMIZER
        try:
            if _PRESIDIO_ANALYZER is None:
                import logging
                logging.getLogger("presidio-analyzer").setLevel(logging.ERROR)
                from presidio_analyzer import AnalyzerEngine
                from presidio_anonymizer import AnonymizerEngine

                _PRESIDIO_ANALYZER = AnalyzerEngine()
                _PRESIDIO_ANONYMIZER = AnonymizerEngine()
            results = _PRESIDIO_ANALYZER.analyze(
                text=scrubbed,
                language="en",
                entities=[
                    "PERSON",
                    "PHONE_NUMBER",
                    "EMAIL_ADDRESS",
                    "CREDIT_CARD",
                    "IBAN_CODE",
                    "IP_ADDRESS",
                    "MEDICAL_LICENSE",
                ],
            )
            scrubbed = _PRESIDIO_ANONYMIZER.anonymize(text=scrubbed, analyzer_results=results).text
        except Exception:
            pass

    redaction_tags = (
        "<REDACTED_API_KEY>",
        "<REDACTED_SECRET_KEY>",
        "<REDACTED_EMAIL>",
        "<REDACTED_IP>",
        "<REDACTED_SECRET>",
        "<REDACTED_SA_ID>",
        "<REDACTED_ID_NUMBER>",
        "<REDACTED_PHONE>",
        "<REDACTED_FINANCIAL_ID>",
        "<REDACTED_BANK_ACCOUNT>",
        "<REDACTED_ADDRESS>",
        "<REDACTED_MEDICAL_INFO>",
        "<PERSON>",
        "<PHONE_NUMBER>",
        "<EMAIL_ADDRESS>",
        "<CREDIT_CARD>",
        "<IBAN_CODE>",
    )
    redaction_count = sum(scrubbed.count(tag) for tag in redaction_tags)
    if redaction_count > 0:
        log_siem_event(
            level="WARNING",
            message=f"[SECURITY_AUDIT] [LOCAL_BROKER_PII] Offline DLP scrubbed {redaction_count} sensitive PII/secret item(s) during '{stage}' stage.",
            module_name="local_brain_broker",
            logger_name="security.local_brain_broker",
        )

    return scrubbed


def _extract_file_text(filepath: str, limit: int) -> str:
    """
    Offline text extractor supporting plain text, Word (.docx), and PDF (.pdf) documents.
    Returns empty string for binary/media files.
    """
    if limit <= 0:
        return ""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".docx":
        try:
            import xml.etree.ElementTree as ET
            import zipfile

            with zipfile.ZipFile(filepath) as z:
                xml_bytes = z.read("word/document.xml")
            tree = ET.fromstring(xml_bytes)
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            paras = []
            curr_len = 0
            for p in tree.iter(f"{ns}p"):
                texts = [t.text for t in p.iter(f"{ns}t") if t.text]
                if texts:
                    line = "".join(texts)
                    paras.append(line)
                    curr_len += len(line) + 1
                    if curr_len >= limit:
                        break
            return "\n".join(paras)[:limit]
        except Exception:
            return ""
    if ext == ".pdf":
        try:
            import pypdf

            reader = pypdf.PdfReader(filepath)
            pages_text = []
            curr_len = 0
            for page in reader.pages:
                pt = page.extract_text() or ""
                if pt:
                    pages_text.append(pt)
                    curr_len += len(pt) + 1
                    if curr_len >= limit:
                        break
            return "\n".join(pages_text)[:limit]
        except Exception:
            return ""
    if ext in _TEXT_EXTENSIONS:
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                return f.read(limit)
        except Exception:
            return ""
    return ""


def read_target_documents(target_path: str, max_chars: int = 8000):
    """
    Reads a single sensitive file or readable files (.txt, .md, .docx, .pdf, .json, etc.)
    inside a sensitive directory (walking up to 2 levels deep).
    Returns (file_list, combined_text).
    """
    target_path = normalize_cross_platform_path(target_path)
    if not os.path.exists(target_path):
        return [], ""

    files_read = []
    chunks = []
    total_len = 0

    if os.path.isdir(target_path):
        base_depth = target_path.rstrip(os.sep).count(os.sep)
        for dirpath, dirnames, filenames in os.walk(target_path):
            curr_depth = dirpath.rstrip(os.sep).count(os.sep) - base_depth
            if curr_depth >= 2:
                dirnames[:] = []
            else:
                dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))

            for entry in sorted(filenames):
                if entry.startswith(".") or entry.startswith("~$") or entry.lower() in _SKIP_FILENAMES:
                    continue
                full_p = os.path.join(dirpath, entry)
                rel_name = os.path.relpath(full_p, target_path)
                content = _extract_file_text(full_p, max(500, max_chars - total_len))
                if content.strip():
                    files_read.append(rel_name)
                    chunks.append(f"--- FILE: {rel_name} ---\n{content}")
                    total_len += len(content)
                    if total_len >= max_chars or len(files_read) >= 12:
                        break
            if total_len >= max_chars or len(files_read) >= 12:
                break
    elif os.path.isfile(target_path):
        fname = os.path.basename(target_path)
        content = _extract_file_text(target_path, max_chars)
        if content.strip():
            files_read.append(fname)
            chunks.append(f"--- FILE: {fname} ---\n{content}")

    return files_read, "\n\n".join(chunks)



def run_local_qwen(system_prompt: str, user_prompt: str, max_tokens: int = 900, target_label: str = "sensitive_vault") -> str:
    """
    Invokes the local Qwen2.5-1.5B-Instruct GGUF model via llama-cli on CPU.
    Loads into RAM only for the duration of this call and exits immediately (0 MB idle RAM).
    """
    if not os.path.exists(LLAMA_CLI) or not os.path.exists(MODEL_PATH):
        log_siem_event(
            level="ERROR",
            message="[FAULT] Local Brain binary or GGUF model missing during sensitive vault invocation.",
            module_name="local_brain_broker",
            logger_name="agent.local_brain_broker",
        )
        return (
            "[LOCAL_BRAIN_UNAVAILABLE] The local Qwen2.5-1.5B model or llama-cli binary "
            "is still downloading or missing at ~/.local/models/."
        )

    cmd = [
        LLAMA_CLI,
        "-m",
        MODEL_PATH,
        "-sys",
        system_prompt,
        "-p",
        user_prompt,
        "-n",
        str(max_tokens),
        "-t",
        "8",
        "-c",
        "4096",
        "--temp",
        "0.2",
        "--no-display-prompt",
        "-st",
        "--log-disable",
    ]

    try:
        res = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            start_new_session=True,
            timeout=90,
        )
        out = res.stdout
        # Extract response after echoed prompt (or its '... (truncated)' marker) and before performance stats
        if "... (truncated)\n" in out:
            out = out.split("... (truncated)\n", 1)[-1]
        else:
            prompt_lines = [line for line in user_prompt.strip().splitlines() if line.strip()]
            if prompt_lines and prompt_lines[-1] in out:
                out = out.split(prompt_lines[-1], 1)[-1]
            elif "\n> " in out:
                out = out.split("\n> ", 1)[-1]
                if "\n" in out:
                    out = out.split("\n", 1)[-1]

        if "[ Prompt:" in out:
            out = out.split("[ Prompt:", 1)[0]
        elif "Exiting..." in out:
            out = out.split("Exiting...", 1)[0]

        out = out.strip()
        for marker in ("<|im_end|>", "<|endoftext|>", "[end of text]"):
            if out.endswith(marker):
                out = out[: -len(marker)].strip()

        est_tokens = max(1, (len(user_prompt) + len(out)) // 4)
        SwarmFlowLogger.log_tuple(
            modder_id="LocalPrivacyBroker",
            agent_id="Qwen2.5-1.5B-CPU",
            target_namespace=target_label,
            model_tier="qwen2.5-1.5b-instruct-q4_k_m (Local CPU)",
            token_volume=est_tokens,
        )
        log_siem_event(
            level="INFO",
            message=f"[AGENTIC] Ephemeral Local Brain (Qwen2.5-1.5B) completed inference on '{target_label}' (~{est_tokens} tokens, 0 MB idle RAM).",
            module_name="local_brain_broker",
            logger_name="agent.local_brain_broker",
        )
        return out
    except subprocess.TimeoutExpired:
        log_siem_event(
            level="ERROR",
            message=f"[FAULT] Local Brain timed out after 90s while processing '{target_label}'.",
            module_name="local_brain_broker",
            logger_name="agent.local_brain_broker",
        )
        return "[LOCAL_BRAIN_TIMEOUT] Local model timed out while processing the sensitive document."
    except Exception as e:
        log_siem_event(
            level="ERROR",
            message=f"[FAULT] Local Brain execution error on '{target_label}': {str(e)}",
            module_name="local_brain_broker",
            logger_name="agent.local_brain_broker",
        )
        return f"[LOCAL_BRAIN_ERROR] {str(e)}"


def is_exfiltration_query(query: str) -> bool:
    """
    Blocks queries from the Online Model that attempt to trick the Local Brain
    into dumping or quoting raw source files verbatim.
    """
    if not query:
        return False
    q_low = query.lower()
    forbidden_phrases = (
        "verbatim",
        "word for word",
        "exact text",
        "raw text",
        "full text",
        "entire file",
        "entire document",
        "dump the",
        "print all",
        "copy paste",
        "repeat the text",
        "quote the entire",
        "base64",
    )
    return any(p in q_low for p in forbidden_phrases)


def strip_verbatim_source_lines(generated_text: str, raw_source: str, target_path: str = "") -> str:
    """
    Ensures the Local Brain never accidentally echoes long raw lines (>60 chars)
    verbatim from the sensitive source file back to the Online Model.
    """
    if not generated_text or not raw_source:
        return generated_text
    raw_lines = {
        line.strip()
        for line in raw_source.splitlines()
        if len(line.strip()) > 60
    }
    if not raw_lines:
        return generated_text
    cleaned_lines = []
    redacted_count = 0
    for out_line in generated_text.splitlines():
        if out_line.strip() in raw_lines:
            cleaned_lines.append("[REDACTED_VERBATIM_SOURCE_LINE]")
            redacted_count += 1
        else:
            cleaned_lines.append(out_line)

    if redacted_count > 0:
        reason = f"[SECURITY_AUDIT] [VERBATIM_LEAK_BLOCKED] Redacted {redacted_count} verbatim source line(s) (>60 chars) from Local Brain output for '{target_path}'."
        log_siem_event(
            level="WARNING",
            message=reason,
            module_name="local_brain_broker",
            logger_name="security.local_brain_broker",
        )
        SwarmFlowLogger.log_intrusion_alert(
            modder_id="LocalPrivacyBroker",
            agent_id="VerbatimLineFilter",
            target_namespace=target_path or "sensitive_vault",
            reason=reason,
        )
    return "\n".join(cleaned_lines)


def generate_digest(target_path: str, custom_query: str = None) -> dict:
    if is_exfiltration_query(custom_query):
        reason = f"[SECURITY_AUDIT] [EXFILTRATION_BLOCKED] Online model attempted forbidden verbatim/raw extraction query on '{target_path}': {custom_query}"
        log_siem_event(
            level="ERROR",
            message=reason,
            module_name="local_brain_broker",
            logger_name="security.local_brain_broker",
        )
        SwarmFlowLogger.log_intrusion_alert(
            modder_id="MainCloudBrain",
            agent_id="ExfiltrationQueryGuard",
            target_namespace=target_path,
            reason=reason,
        )
        return {
            "status": "BLOCKED_EXFILTRATION_ATTEMPT",
            "error": "Raugus Local Broker: Requests for verbatim or raw source dumps are strictly forbidden. Ask for synthesized summaries or exam questions only.",
        }

    files, raw_text = read_target_documents(target_path)
    if not files:
        return {
            "status": "EMPTY",
            "target": target_path,
            "files": [],
            "digest": "No readable documents found in the sensitive directory yet.",
        }

    # Pre-scrub raw text before feeding to local model for defense-in-depth
    pre_scrubbed = offline_scrub_pii(raw_text, stage="input_digest")

    sys_prompt = (
        "You are the Raugus Local Privacy Broker AI running offline on the user's machine. "
        "Your job is to read sensitive local documents and provide a useful, sanitized summary "
        "or topic outline for the Main Cloud Brain WITHOUT revealing any raw passwords, API keys, "
        "personal names, emails, or confidential verbatim quotes."
    )
    if custom_query:
        u_prompt = (
            f"SENSITIVE DOCUMENT CONTENT:\n{pre_scrubbed}\n\n"
            f"MAIN BRAIN REQUEST: {custom_query}\n\n"
            "Provide a clear, accurate, sanitized answer that fulfills the Main Brain's request "
            "without leaking raw secrets, PII, or verbatim paragraphs."
        )
    else:
        u_prompt = (
            f"SENSITIVE DOCUMENT CONTENT:\n{pre_scrubbed}\n\n"
            "Provide:\n"
            "1. A concise 3-5 bullet summary of the core educational/technical topics covered.\n"
            "2. Key concepts that can be used to generate exam or quiz questions.\n"
            "Do NOT output raw credentials, personal names, or secret keys."
        )

    reply = run_local_qwen(sys_prompt, u_prompt, max_tokens=600, target_label=f"digest:{target_path}")
    safe_reply = strip_verbatim_source_lines(offline_scrub_pii(reply, stage="output_digest"), raw_text, target_path=target_path)
    return {
        "status": "OK",
        "target": target_path,
        "files": files,
        "local_model": "qwen2.5-1.5b-instruct-q4_k_m (CPU Ephemeral)",
        "response": safe_reply,
    }


def generate_exam_questions(target_path: str, count: int = 5, custom_query: str = None) -> dict:
    if is_exfiltration_query(custom_query):
        reason = f"[SECURITY_AUDIT] [EXFILTRATION_BLOCKED] Online model attempted forbidden verbatim/raw extraction query in exam mode on '{target_path}': {custom_query}"
        log_siem_event(
            level="ERROR",
            message=reason,
            module_name="local_brain_broker",
            logger_name="security.local_brain_broker",
        )
        SwarmFlowLogger.log_intrusion_alert(
            modder_id="MainCloudBrain",
            agent_id="ExfiltrationQueryGuard",
            target_namespace=target_path,
            reason=reason,
        )
        return {
            "status": "BLOCKED_EXFILTRATION_ATTEMPT",
            "error": "Raugus Local Broker: Requests for verbatim or raw source dumps are strictly forbidden. Ask for synthesized summaries or exam questions only.",
        }

    files, raw_text = read_target_documents(target_path)
    if not files:
        return {
            "status": "EMPTY",
            "target": target_path,
            "files": [],
            "error": "No readable documents found in the sensitive directory to generate exam questions from.",
        }

    pre_scrubbed = offline_scrub_pii(raw_text, stage="input_exam")

    sys_prompt = (
        "You are the Raugus Local Exam Broker AI. Read the sensitive source material and generate "
        "educational exam questions in strict JSON format. Never include raw passwords, API keys, "
        "or personal PII in the questions or explanations. Output ONLY valid JSON."
    )
    extra_instructions = f"\nAdditional instructions from Main Brain: {custom_query}\n" if custom_query else ""
    u_prompt = (
        f"SOURCE MATERIAL:\n{pre_scrubbed}\n"
        f"{extra_instructions}\n"
        f"Generate exactly {count} exam questions based on the concepts in the source material. "
        "Output ONLY a valid JSON object matching this exact schema:\n"
        "{\n"
        '  "questions": [\n'
        "    {\n"
        '      "type": "multiple_choice",\n'
        '      "text": "Question text here?",\n'
        '      "options": ["Option A", "Option B", "Option C", "Option D"],\n'
        '      "correct_index": 0,\n'
        '      "explanation": "Clear explanation of why Option A is correct."\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules:\n"
        '- Use "text" (NEVER "question").\n'
        '- For "multiple_choice", use integer "correct_index" (0-based).\n'
        '- For "dropdown_blank", include exactly one "[BLANK]" in "text", an "options" list, and string "correct_text".\n'
        "- Return ONLY the raw JSON object without markdown code fences."
    )

    reply = run_local_qwen(sys_prompt, u_prompt, max_tokens=1400, target_label=f"exam:{target_path}")
    safe_reply = strip_verbatim_source_lines(offline_scrub_pii(reply, stage="output_exam"), raw_text, target_path=target_path)

    # Extract JSON object if wrapped in markdown fences
    json_match = re.search(r"\{[\s\S]*\}", safe_reply)
    parsed_questions = None
    if json_match:
        try:
            parsed_questions = json.loads(json_match.group(0))
        except Exception:
            parsed_questions = None

    return {
        "status": "OK",
        "target": target_path,
        "files": files,
        "local_model": "qwen2.5-1.5b-instruct-q4_k_m (CPU Ephemeral)",
        "exam_payload": parsed_questions if parsed_questions else safe_reply,
    }


def main():
    parser = argparse.ArgumentParser(description="Raugus Local Brain Privacy Broker")
    parser.add_argument("--target", required=True, help="Sensitive file or directory path")
    parser.add_argument(
        "--mode",
        choices=["digest", "exam", "query"],
        default="digest",
        help="Mode: 'digest' for topic summary, 'exam' for exam JSON generation, 'query' for Q&A",
    )
    parser.add_argument("--query", default=None, help="Specific prompt/instructions from the Main Brain")
    parser.add_argument("--count", type=int, default=5, help="Number of exam questions to generate")
    args = parser.parse_args()

    if args.mode == "exam":
        res = generate_exam_questions(args.target, count=args.count, custom_query=args.query)
    else:
        res = generate_digest(args.target, custom_query=args.query)

    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
