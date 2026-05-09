# How AssemblyAI Handles Your Data: Privacy and Retention for Spanglish Inc.

---

## 1. What Happens to Your Data by Default on Streaming v3

When you connect to AssemblyAI's Universal Streaming v3 endpoint without additional configuration, here's the data flow:

**In transit:** All audio frames and transcripts travel over TLS 1.3, encrypted end-to-end. No plain-text audio leaves your client.

**At rest:** Audio is processed in memory and streamed to your client in real time. AssemblyAI does not buffer or store your audio on disk by default, except for brief staging buffers (milliseconds) during processing.

**Model training:** By default, on paid plans, AssemblyAI may retain and use your transcripts and deidentified audio samples to improve the ASR models. This is the industry standard for speech-to-text providers. If you have not explicitly opted out, assume your data is part of the model training pipeline.

**Metadata:** AssemblyAI retains minimal metadata for billing, abuse prevention, and session logging. This includes: session start/end timestamps, connection duration, token counts, error events, and API key hashes. This metadata is never deleted and is necessary for billing accuracy and security audits.

---

## 2. Achieving Zero Data Retention

If Spanglish requires zero retention of audio and transcripts (e.g., due to confidentiality of court proceedings), follow these steps:

### Step 1: Upgrade to a Paid Plan
Free tier users cannot opt out of the model improvement program. Streaming v3 is only available to paid accounts (Standard, Professional, or Enterprise). Confirm your account is on a paid plan.

### Step 2: Opt Out of Model Training
Contact AssemblyAI Support (live chat or email via https://www.assemblyai.com/contact/support) from your account-registered email address. State plainly: "I request to opt out of the model improvement program for all current and future usage on this account."

AssemblyAI will respond with confirmation within 2-5 business days. The opt-out becomes effective upon that confirmation.

### Step 3: Execute a Data Processing Addendum (DPA)
If you have not already, request a DPA from your Customer Success Manager. The DPA is standard on all AssemblyAI paid plans and clarifies:
- Data residency (default: US East 1; EU option available via Dublin residency).
- Processor obligations under GDPR and CCPA.
- Audit rights and deletion timelines.
- Subprocessor disclosures.

### Step 4 (If Applicable): Execute a Business Associate Agreement (BAA)
If Spanglish processes Protected Health Information (PHI) under HIPAA, for example if court interpreters work with healthcare providers or medical testimony, request a BAA. The BAA commits AssemblyAI as a HIPAA Business Associate. With a BAA in place and model training opted out, AssemblyAI offers zero retention of audio, transcripts, and most operational metadata.

### Step 5: Enable Audit Logging
Request access to AssemblyAI's audit logs via the dashboard or API. These logs show: every connection established, transcript retrieved, and data deletion request processed. Review them monthly to confirm no unexpected data access.

### Step 6 (Optional): Use Scoped Streaming Tokens
Instead of using your primary API key for Streaming v3, create temporary, read-only tokens scoped to specific features. This limits the blast radius if a token is ever leaked. See the Streaming v3 API reference for token scoping.

---

## 3. What Is Retained After Opt-Out

**With model training opted out and no BAA:**
- Audio: Deleted immediately after processing (not persisted).
- Transcripts: Retained for 1-72 hours, then deleted (configurable via TTL settings).
- Metadata: Billing and logging metadata retained indefinitely (necessary for billing accuracy and legal holds).

**With model training opted out AND BAA executed:**
- Audio: Deleted immediately, zero retention.
- Transcripts: Deleted immediately, zero retention.
- Metadata: Billing metadata retained indefinitely; operational logs retained for 30-90 days, then deleted.

In both cases, metadata for billing and abuse prevention is never deleted, because AssemblyAI must be able to reconcile charges and investigate suspicious activity even years after a session ends.

---

## 4. Compliance and Standards

AssemblyAI holds the following certifications and compliances:

- **SOC 2 Type II (2025):** Audited security, availability, processing integrity, confidentiality, and privacy controls.
- **PCI-DSS v4.0 Level 1 (effective March 31, 2025):** Compliance with payment-card industry security standards, even though AssemblyAI does not directly process payment cards.
- **GDPR:** DPA + Standard Contractual Clauses (SCCs) allow lawful data transfers to the US. EU data residency available via Dublin.
- **CCPA / CPRA:** California privacy laws incorporated into the DPA.
- **HIPAA:** BAA available for accounts processing PHI.
- **ISO 27001:2022:** Information security management system certification.

For court proceedings specifically, AssemblyAI cannot guarantee legal compliance with wiretapping, recording consent, or other judicial rules. Those responsibilities fall on Spanglish and the court system. Coordinate with your legal team to ensure your audio capture, storage, and retention practices comply with local wiretap statutes and court rules.

---

## 5. What Sits on Spanglish's Side

AssemblyAI is the data *processor*; Spanglish is the *controller*. This means:

- **Consent capture:** You must obtain consent from all speakers before recording (judge, interpreter, parties, witnesses). AssemblyAI cannot do this on your behalf.
- **Your data copy:** Once AssemblyAI returns a transcript, you own that transcript. You are responsible for storing it securely, encrypting it at rest, and deleting it according to your own retention policy.
- **Data subject requests:** If a speaker later requests deletion of their data (GDPR Right to Erasure), you must delete your own copy. AssemblyAI will delete its copy upon confirmation of the opt-out, but you manage the legal obligation to the data subject.
- **Wiretap and consent law compliance:** Recording laws vary by state. Some states require two-party consent (all speakers must consent). Others allow one-party consent. Spanglish must verify compliance with applicable law before recording. AssemblyAI cannot provide legal advice on this.

---

## 6. What We Will Not Promise

- **Legal representation:** We cannot serve as your lawyer. A DPA and BAA are agreements, not legal opinions. For questions on HIPAA applicability, state wiretap laws, or court-proceeding rules, consult your legal counsel.
- **Certification letters:** Vendor "certification" letters (e.g., "we are HIPAA compliant") are not legal documents and do not establish a legal relationship. The BAA is the legal document.
- **Unlimited audit rights:** Audit rights are defined in the DPA and BAA, not unlimited. They are subject to confidentiality and operational constraints.
- **Retroactive opt-out:** Once you opt out of model training, the opt-out applies only to future data. Historical data already used for training cannot be retroactively removed from the model.

---

## 7. Recommended Configuration for Spanglish

Based on your use case (court-interpreter note-takers, mixed English/Spanish, confidential proceedings):

1. **Account tier:** Professional or Enterprise (required for BAA and audit support).
2. **Model training:** Opted out (request via https://www.assemblyai.com/contact/support).
3. **Agreements:** Execute DPA (standard) and BAA (if any PHI is involved).
4. **Data residency:** US East 1 (default) or EU/Dublin if required by court jurisdiction.
5. **Audit logging:** Enabled and reviewed monthly.
6. **Token scoping:** Use temporary, read-only tokens for Streaming v3 connections.
7. **Your retention:** Define your own transcript retention policy (e.g., delete after 30 days, or retain indefinitely in encrypted archive) and enforce it in your application.
8. **Legal review:** Have your legal team review the DPA and BAA before signature. They may request modifications (e.g., subprocessor list, deletion timeline).

---

## 8. Next Steps

1. **Confirm your plan tier** (Professional or Enterprise required).
2. **Opt out of model training** via https://www.assemblyai.com/contact/support.
3. **Request DPA and BAA** from your Customer Success Manager.
4. **Share with your legal team** for review and signature.
5. **Enable audit logging** once agreements are executed.
6. **Schedule a brief security review** with AssemblyAI's trust team if you have additional compliance questions.

Your Customer Success Manager can facilitate all of the above. This is standard for enterprise customers, and we can move quickly.
