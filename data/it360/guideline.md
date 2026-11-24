# IT-250 / HR-200 / MED-200 / IT-300 / MED-300 / HR-300 / IT-360 / MED-360 / HR-360 annotation guideline (v1.7)

This guideline is the only authority for the IT-250, HR-200, MED-200, IT-300, MED-300, HR-300, IT-360, MED-360 and HR-360 benchmarks. v1.2 = v1.1 plus
section 7 (HR clarifications); v1.3 = v1.2 plus two OTHER_ID types (MEDICAL_RECORD_NUMBER, PROFESSIONAL_ID) and
section 8 (medical clarifications). **v1.4 (IT-300)** adds two fine types, FINANCIAL_AMOUNT (FINANCIAL) and JOB_TITLE
(new coarse bucket OCCUPATION), and section 9. Under v1.4, money amounts and job titles linked to a natural person ARE
personal data; the "not tagged" lists in sections 4, 7 and 8 are amended accordingly. **v1.5 (MED-300)** adds section
10 (money amounts and job titles in medical documents) and changes no earlier rule. **v1.6 (HR-300)** adds section
11 (money amounts and job titles in HR documents) and changes no earlier rule. **v1.7 (IT-360, MED-360, HR-360)**
adds section 12 (Danish documents) and changes no earlier rule. IT-250, HR-200 and MED-200 were
annotated under v1.3 and contain neither new type. It was written fresh for this benchmark and is
deliberately vendor-neutral. When in doubt, ask: *would a careful EU data-protection officer want this string removed
before the document leaves the organisation, because it identifies or describes a natural person?*

## 1. Tag syntax
Mark every span inline as `⟦TYPE|exact text⟧`. Rules:
- `TYPE` is one of the fine types in section 3, in upper case.
- The text between `|` and `⟧` must be exactly the characters of the document, so never correct, translate or reformat it.
- Tags never nest and never overlap. Where two types compete, section 5 decides.
- Removing all tags (`⟦TYPE|` and `⟧`) must reproduce the plain document exactly, including whitespace and newlines.
- The characters `⟦` and `⟧` are never used anywhere else in a document. A plain `|` is allowed in the text (tables, pipes in logs), but never inside a tagged value.

## 2. General principles
1. **Every occurrence** gets tagged, including repeats, short forms ("Jan", "Mr Peeters", "J. Peeters"), possessives
   (tag "Anna" in "Anna's laptop") and occurrences inside JSON, YAML, CSV, log lines, URLs and email headers.
2. **Identifiable natural persons only.** Data about a company, a server or a product is not PII (but see ORGANISATION).
   A sole trader's name is a PERSON.
3. **Real vs placeholder.** Obvious template placeholders are NOT tagged: `john.doe@example.com` in a "format:" hint,
   `<username>`, `XXXX-XXXX`, `Jan Modaal`/`Max Mustermann`/`Jean Dupont`/`Jan Kowalski`/`Joe Bloggs` used as
   explicit sample names, `192.0.2.x` shown as documentation examples. A value that is clearly used as real data in
   the document (a ticket says "user jan.kowalski@firma.pl reported…") IS tagged, even if it looks generic.
4. **Span boundaries:** take the minimal span that contains the whole value. Exclude titles and honorifics (Dr, Mr,
   Mme, Herr, Pan, dhr.), surrounding quotes, brackets and trailing punctuation. Include internal spaces, dots and
   dashes that belong to the value (`BE71 0961 2345 6769`, `+32 470 12 34 56`).
5. **Field labels are not part of the span**, so "IBAN: " and "PESEL " stay outside the tag.

## 3. Fine types

### NAME
- **PERSON**: given name, surname or both, including nicknames used as names in chat. A person's initials alone
  ("JP approved") are tagged only when they clearly refer to a specific person in the document.
- **USERNAME**: a login, handle, account name or mailbox alias tied to a person (`jkowalski`, `@lotte.b`,
  `DOMAIN\pkrol`). Tag only the name part: in `CORP\pkrol`, tag `pkrol`. Service accounts (`svc_backup`, `root`,
  `admin`) are not PERSON-tied, so they are NOT tagged.

### CONTACT
- **EMAIL**: personal or work addresses of a person. Shared role mailboxes (`helpdesk@`, `noreply@`, `dpo@`,
  `security@`) are NOT tagged.
- **PHONE**: a person's mobile or direct-dial number in any format. Switchboard, helpdesk and company main numbers are
  NOT tagged.

### LOCATION (split into components, each its own span)
- **STREET_ADDRESS**: street + house number, including box, flat or apartment parts ("Flat 4, 12 Wren Lane",
  "Lindenstraße 14a", "ul. Polna 7/12", "Molenstraat 3 bus 2"). Street type words and the "ul." prefix are
  inside the span.
- **POSTCODE**: the postal code, including a country prefix that is written together with it ("L-1234").
- **CITY**: any city, town or municipality name, inside an address or on its own ("works from the Leuven office",
  "relocated to Kraków"). A city that is part of a company name or a product name is not tagged ("Berlin Brands
  Group"). Countries, regions and data-centre region codes (`eu-west-1`, "Frankfurt region") are NOT CITY. A city in an
  airport code, timezone ID or hostname (`Europe/Paris`, `ams-dc2`) is NOT tagged.
  These rules apply to company addresses too, so the whole address of an organisation is tagged (street, postcode,
  city).

### DATE
- **DATE_OF_BIRTH**: only dates presented as someone's birth date. Ages, ticket dates and contract dates are NOT tagged.

### GOV_ID
- **NATIONAL_ID**: national identity or registry numbers of a person: PESEL, BSN, Belgian national register number,
  French NIR/numéro de sécurité sociale, Luxembourg matricule, Austrian SV-Nummer, Swiss AHV, Irish PPSN, UK NINO,
  German Personalausweis number, German Sozialversicherungs-/Rentenversicherungsnummer, Maltese ID card number.
- **TAX_ID**: a personal tax number (Steuer-ID, numéro fiscal/SPI, NIP of a person, UTR, Austrian Steuernummer).
  Company VAT and registry numbers are tagged as TAX_ID as well, because they identify sole traders and are routinely
  redacted. A person's BSN/PPSN/RRN stays NATIONAL_ID even when it is used for tax.
- **PASSPORT**, **DRIVERS_LICENSE**: the document number.
- **VEHICLE_PLATE**: number plates.

### FINANCIAL
- **IBAN**: full IBAN, or the domestic account form of the same number (Polish NRB without "PL").
- **PAYMENT_CARD**: a full card number, or a masked card number that still shows 4 or more digits ("**** 5745" is tagged
  as a whole).
- **FINANCIAL_AMOUNT** (v1.4): a money amount linked to an identifiable natural person, whether the person pays it or
  receives it: what a private customer or sole trader is invoiced, owes, pays or is refunded; a freelancer's fee, day
  rate or invoice total; a salary, bonus, allowance, expense reimbursement or payroll deduction of an employee. See
  section 9 for spans and for what is not tagged.

### NETWORK
- **IP_ADDRESS**: IPv4/IPv6 addresses that relate to a person's device or session (VPN client IP, login source IP,
  a workstation IP in a log). Public server and vendor IPs in configs are also tagged, since they can be personal
  when tied to a user's session. Documentation-example IPs shown as examples, network ranges in CIDR notation
  (`10.0.0.0/8`) and `127.0.0.1`/`0.0.0.0` are NOT tagged.
- **MAC_ADDRESS**: any MAC address.
- **PERSONAL_URL**: a URL whose path or host contains a person's identifier (`https://git.firm.nl/pkrol`). Tag the
  whole URL. Generic URLs are NOT tagged.

### CREDENTIAL
- **SECRET**: passwords, API keys, access tokens, JWTs, private keys and connection strings with an embedded password;
  also one-time login or verification codes (SMS/OTP codes) of a person *(clarified at adjudication, v1.4)*.
  For a connection string, tag the whole string. Hashes that are explicitly labelled as hashes and redacted values
  (`****`) are NOT tagged.

### OTHER_ID
- **EMPLOYEE_ID**, **CUSTOMER_ID**: identifiers of a person in an organisation's systems (personnel number, customer
  or contract-holder number, badge number).
- **MEDICAL_RECORD_NUMBER** (v1.3): a patient's number in a care provider's records: hospital number, MRN, IPP,
  Patienten-ID, patiëntnummer, ID pacjenta, a GP practice's patient number, a hospital case/stay number
  (Fallnummer, numéro de séjour). Specimen, order, accession, prescription and appointment numbers are NOT tagged.
- **PROFESSIONAL_ID** (v1.3): a clinician's registration or licence number: GMC, NMC, HCPC, GPhC, IMC, NMBI, RPPS,
  ADELI, INAMI/RIZIV, LANR, GLN, BIG, PWZ, Maltese Medical Council number.
- **DEVICE_SERIAL**: the serial number or asset tag of a device assigned to a named or identifiable person. Serials of
  servers or unassigned stock are NOT tagged.
  Ticket numbers, order numbers, change IDs, CVE IDs, version and build numbers, hostnames and asset IDs of servers are
  NOT tagged.

### OCCUPATION (v1.4)
- **JOB_TITLE**: a job title, function, role or occupation attributed to an identifiable natural person ("Anna Nowak,
  Head of IT", a signature block "Systems Administrator", "our DPO Marc Lenaerts", "the new sysadmin" when that person
  is named or otherwise identified in the document, a customer's occupation "teacher"). Generic roles that do not
  point to one identifiable person are NOT tagged (see section 9).

### SPECIAL: GDPR Art. 9 special categories (phrase level)
Tag the **minimal phrase that states the attribute of an identifiable person**. The phrase is the attribute itself
("type 1 diabetes", "is pregnant", "member of ver.di", "practising Muslim"), not the whole sentence, and not the person's
name (which gets its own PERSON tag).
- **HEALTH**: physical or mental health conditions, disabilities, diagnoses, treatments, medication, sick leave *with
  a reason*, pregnancy, accessibility needs that reveal a condition ("needs a screen reader due to his visual
  impairment" → tag "visual impairment"). A bare "on sick leave" with no condition IS tagged as HEALTH, because absence
  for sickness is health data.
- **ETHNIC_ORIGIN**: racial or ethnic origin ("of Roma origin", "Moroccan-Dutch background"). Nationality or a
  working language is NOT this type.
- **POLITICAL_OPINION**: party membership, political activity or opinions attributed to the person.
- **RELIGION_BELIEF**: religion or philosophical beliefs ("observes Shabbat", "prayer-room badge for Friday prayers",
  "requested halal catering for religious reasons").
- **TRADE_UNION**: union membership or role ("CGT shop steward", "FNV-lid", "Solidarność representative").
- **GENETIC**: genetic test results, hereditary conditions identified genetically.
- **BIOMETRIC**: biometric data *used to identify* a person, such as enrolled fingerprint or face templates, voiceprints,
  a template ID that refers to that person ("fingerprint template enrolled", "Face ID template FT-88213"). A
  general mention that a device has a fingerprint reader is NOT tagged.
- **SEX_LIFE_ORIENTATION**: sexual orientation or sex life ("his husband", "came out as gay",
  "LGBTQ+ employee network lead" when it reveals the person's orientation).

### CRIMINAL: GDPR Art. 10 (phrase level)
- **CRIMINAL_OFFENCE**: criminal convictions, offences, ongoing criminal proceedings, police reports naming a suspect,
  the content of a criminal-record certificate ("conviction for fraud in 2019", "under investigation for data theft",
  "Führungszeugnis contains an entry"). A *clean* record ("certificate shows no entries") IS tagged, because it is
  still Art. 10 data. Requesting a certificate without stating any result is NOT tagged.

**Generic mentions are not tagged.** A DPA clause listing "health data" as a processing category, a policy saying
"criminal records must be stored encrypted", or a form field label "Religion:" with no value is not about an
identifiable person.

### ORG
- **ORGANISATION**: names of companies, public bodies, schools, hospitals and vendors (including real ones such as
  Microsoft or Atlassian). It is annotated for reference with `redact:false` and scored separately. Union names inside
  a TRADE_UNION phrase are the exception, since they are part of that phrase.

## 4. Things that are never tagged
Product and software names, version numbers, CVEs, ticket/order/change numbers, hostnames of servers, generic role
titles that do not point to an identifiable person ("administrators must…", "contact your DPO"), countries, languages,
dates other than DOB, prices and amounts that are not linked to a natural person (section 9), hashes, file paths
without a username, and service accounts.

A file path or hostname that contains a person's username, such as `C:\Users\pkrol\` or `laptop-pkrol`, is the exception:
tag the username part as USERNAME (`pkrol`). A server whose hostname merely sounds like a person (`anna-db01`,
`HERMES`, `jupiter`) is NOT tagged unless the document says the name belongs to a person.

## 5. Conflicts
- An email address is EMAIL as a whole, so the name inside it is not tagged separately.
- A PERSONAL_URL is tagged as a whole.
- A city inside a company name is not tagged. A city in that company's address is.
- A person name inside a special-category phrase gets no tag of its own. Tag the name outside the phrase where
  possible, and keep the phrase minimal so the two don't touch.
- A union name inside a TRADE_UNION phrase is part of that phrase and not a separate ORGANISATION.

## 6. Clarifications (v1.1, settled after the generation pass)
- **Masked values:** tag a partially masked value with its type when at least 4 characters of the original value
  are still visible (an email's domain counts): `**** **** **** 5745`, `j***@webmail.test`, `*******2155`. A value
  with fewer than 4 visible original characters, or fully masked (`****`, `AKIA****`), is not tagged.
- **Initials and abbreviations:** "Benoît L.", "M. Jacobs" and "P. Mazur" are PERSON, and the abbreviation dot is
  inside the span. Initials used as a sign-off for a known person ("BvL", "WB") are PERSON.
- **Inflected forms:** a name or city written in an inflected or genitive form as one word is tagged as the whole
  word ("Kamila Pawłowskiego", "w Katowicach", "Annas Laptop"). The English possessive `'s` stays outside.
- **Vendors inside product names:** a vendor name that is part of a product name is not tagged ("Microsoft
  Authenticator", "Lenovo ThinkPad", "AWS Config"). A vendor acting as a party ("Microsoft confirmed…", "invoice from
  Atlassian") is ORGANISATION.
- **Cities inside names of courts, registries and public bodies** ("Amtsgericht Leipzig", "rechtbank Amsterdam",
  "RCS Paris", "tribunal de commerce de Lyon") are part of that ORGANISATION or TAX_ID reference and are not tagged
  CITY. When a registry reference such as "RCS Paris 123 456 789" is written as one unit, the whole unit is TAX_ID.
- **Sole-trader trade names** that contain a person's name: tag the name part as PERSON ("EI ⟦PERSON|Schmitz⟧ Conseil").
- **URLs with personal data in the query string only:** tag the parts (USERNAME, EMAIL, DATE_OF_BIRTH…) and not the
  URL. PERSONAL_URL is used only when the host or path carries the identifier. It then covers the whole URL including
  any later path or query.
- **Back-references to an Art. 9/10 fact** stated about the same person are tagged too ("the HR note about the
  ⟦CRIMINAL_OFFENCE|conviction⟧").
- **Organisation names written in capitals or as a lookalike sender display name** are still ORGANISATION.
- **Server and infrastructure IPs:** every concrete IP address is tagged (section 3), including private
  server and printer IPs. Exceptions are documentation-example IPs shown as examples, CIDR ranges, `127.0.0.1` and
  `0.0.0.0`.

## 7. HR clarifications (v1.2)
- **Sickness, disability, pregnancy.** Sick leave (also without a reason), a diagnosis, a disability status or degree
  ("GdB 50", "RQTH", "registered disabled", "Wajong"), pregnancy, maternity leave, an injury from a work accident, an
  occupational-health restriction ("no night shifts for medical reasons") and a drug or alcohol test result are
  HEALTH. Parental, paternity, care or compassionate leave with no health detail is NOT HEALTH.
- **Church tax and religion fields.** A denomination recorded for a person ("Konfession: rk", "Kirchensteuermerkmal
  ev", "Religion: Muslim") is RELIGION_BELIEF; tag the value, not the label. "konfessionslos"/"none" recorded for a
  person is RELIGION_BELIEF too (it states the person's belief status). A field label without value is not tagged.
- **Union membership.** Union dues deducted from a person's pay ("Gewerkschaftsbeitrag ver.di", "cotisation
  syndicale CFDT") is TRADE_UNION. A union named only as a negotiating party, signatory or organiser, with no
  person's membership stated, is ORGANISATION.
- **Partners and family.** Names of partners, children and emergency contacts are PERSON. A partner mention is
  SEX_LIFE_ORIENTATION only when it reveals a sexual orientation or sex life (a same-sex partner, "came out",
  "LGBTQ+ network lead" about themselves). A different-sex spouse or partner is not tagged as SEX_LIFE_ORIENTATION.
- **Criminal vs disciplinary.** An alleged or established criminal act attributed to a person (theft, fraud,
  assault, drink-driving, a police report, a court case, a criminal-record certificate result) is CRIMINAL_OFFENCE,
  also when handled internally. A purely disciplinary breach that is not a crime (lateness, misuse of the internet
  policy, rudeness) is not tagged.
- **Nationality, residence and language** are not ETHNIC_ORIGIN (section 3). Ethnic origin recorded or stated about a
  person (a monitoring-form answer, "of Kurdish origin") is.
- **Aggregate figures** ("4 employees declared a disability", "12% of staff are union members") are not about an
  identifiable person and are not tagged, unless the group is so small that the document names or singles out the
  person.
- **Not tagged in HR documents:** (v1.4: salaries and other amounts of a person are FINANCIAL_AMOUNT and a person's
  job title is JOB_TITLE; the rest of this item is unchanged) grades, departments, contract types, hire
  and leave dates (only DOB is a DATE type), legal references (Art. 9(2)(b) GDPR, § 26 BDSG), court case numbers.
- **Insurance and pension membership numbers** of a person are CUSTOMER_ID.

## 8. Medical clarifications (v1.3)
- **Health items, one span each.** Tag every health statement about an identifiable person as its own HEALTH span:
  a condition, diagnosis, symptom, injury, allergy, disability, pregnancy or obstetric status ("38+2 weeks pregnant",
  "G2P1"), mental-health state, substance use, cause of death; a medication together with its dose, route and
  frequency ("metformin 1 g twice daily", "Ramipril 5 mg 1-0-0"); a procedure, operation, therapy or care event
  that reveals health ("laparoscopic cholecystectomy", "admitted to the stroke unit", "third cycle of
  chemotherapy"); a test or measurement together with its result ("HbA1c 64 mmol/mol", "BP 158/94", "BMI 31",
  "HIV test negative"). Items joined by "and" or commas are separate spans ("hypertension and type 2 diabetes" →
  two spans); a qualifier belongs to its item ("type 2 diabetes with nephropathy", "fracture of the left radius").
- **Normal, negative and ruled-out findings are HEALTH** ("no evidence of metastases", "CRP normal", "COVID-19
  PCR negative"): they are still health data about the person.
- **Tests ordered without a result** are not tagged ("full blood count requested"), unless the test itself reveals
  a condition or risk ("HIV test", "pregnancy test", "BRCA testing requested"), which is HEALTH (or GENETIC for a
  genetic test).
- **Labels, headers and template text** ("Diagnosis:", "Medication:", "Allergies:") stay outside the span; the value
  after the label is tagged, including a negative value ("Allergies: ⟦HEALTH|none known⟧"); in tables and lists each value
  cell or item is its own span. Body-site words, laterality and units are inside the span.
- **Departments, wards and clinics.** A department or ward in a letterhead, address, signature or routing line is
  not tagged ("Department of Cardiology", "Ward 7B"). When a clinic, ward or service name is linked to the patient
  and reveals their condition ("seen in the HIV clinic", "admitted to the oncology ward", "under the memory
  clinic"), tag that name as HEALTH ("HIV clinic", "oncology ward", "memory clinic"). A clinic that is the issuing
  institution named in full ("Fernleigh Mental Health Service") is ORGANISATION.
- **Job titles and specialties** of clinicians ("consultant cardiologist", "Hausärztin", "verpleegkundige") are not
  tagged, also when they hint at the patient's condition. (v1.4: a clinician's job title linked to that clinician is
  JOB_TITLE; MED-200 does not contain it.)
- **Eponyms** (Parkinson's disease, Crohn's disease, Down syndrome, Hodgkin lymphoma, Apgar score, Babinski sign) are
  part of a HEALTH span and never PERSON.
- **Age, sex, height on its own, dates of admission, discharge, surgery or appointments** are not tagged. Weight,
  BMI and other measurements with a value are HEALTH. The date a baby was born is that baby's DATE_OF_BIRTH.
- **GENETIC** covers genetic test results, variants and genotypes ("BRCA2 c.5946delT pathogenic variant",
  "heterozygous for HFE C282Y"), carrier or predictive status ("carrier of cystic fibrosis", "tested positive for
  the Huntington expansion"), karyotypes and prenatal genetic results ("NIPT low risk"), also of identifiable
  relatives. A hereditary disease named as a diagnosis without a genetic result ("cystic fibrosis") is HEALTH.
- **BIOMETRIC** is a fingerprint, face, palm-vein or voice template used to identify a patient or staff member
  (medication-cabinet fingerprint login, palm-vein patient identification, face login to a portal, a template ID).
  Medical images and signals (X-rays, retinal photographs, ECGs) are HEALTH, not BIOMETRIC.
- **ETHNIC_ORIGIN** is ethnicity recorded or stated in the record ("of Ashkenazi Jewish ancestry", "ethnicity: Black
  Caribbean"). Country of birth, nationality, language and an interpreter need are not.
- **RELIGION_BELIEF** is a religion or belief relevant to care ("Jehovah's Witness", "observes Ramadan", "asks for an
  imam", "kosher diet for religious reasons"). The treatment decision itself ("declines blood products") is HEALTH.
- **SEX_LIFE_ORIENTATION** is sexual orientation or sexual behaviour ("MSM", "has sex with men and women", "two new
  partners in the last three months", "her wife"). Sexually transmitted infections, contraception and PrEP are
  HEALTH.
- **CRIMINAL_OFFENCE** is an offence alleged or established of an identifiable person: police custody or arrest,
  a charge or conviction, a drink-driving test requested by the police, a forensic order ("detained under s.37 after
  a conviction for arson", "the partner has been charged with assault"). Being the victim of a crime is not an
  offence of the victim; the injuries are HEALTH.
- **Identifiers.** NHS number, Krankenversichertennummer, NIR / carte Vitale number, INSZ/NISS, BSN, PESEL,
  SV-Nummer, AHV and PPSN are NATIONAL_ID. Health-insurance member, policy and membership numbers are CUSTOMER_ID.
  Staff numbers are EMPLOYEE_ID. The serial number of an implant or a medical device used by a patient is
  DEVICE_SERIAL. Study subject and screening codes ("subject 104-017"), bed and room numbers, specimen and order
  numbers are NOT tagged.


## 9. IT-300 clarifications (v1.4): money amounts and job titles

### 9.1 FINANCIAL_AMOUNT
- **What is tagged.** Every money amount that is linked to an identifiable natural person as payer or payee:
  - on an invoice, quote, receipt, order confirmation, payment reminder, refund or credit note addressed to a private
    customer or a sole trader: unit prices, line totals, discounts, VAT amounts, totals, amounts paid, balances due,
    instalments, deposits, late fees;
  - on a freelancer's own invoice, timesheet or purchase order: day or hourly rate, line amounts, total;
  - an employee's salary, bonus, allowance (home-office, phone, BYOD), expense reimbursement, payroll deduction
    (e.g. for a lost or damaged laptop), a fine or charge recharged to a named person;
  - an amount in a payment-card or bank transaction of a person (a log line `amount=49.99 EUR` for a named customer,
    a refund of €12,99 to a customer's card).
- **Span.** The amount with its currency symbol or code exactly as written, including thousands separators, decimals
  and a minus sign: `€ 1.234,50`, `1 234,50 zł`, `EUR 89.00`, `£12.99`, `CHF 2'450.–`, `-€15,00`. Words around it stay
  outside ("per month", "excl. VAT", "/h", "incl. BTW"). In a table whose currency is only in the column header, tag
  the bare number in each cell (`89,00`). Each amount is its own span. Amounts written in words are tagged as written.
- **Not tagged.** Amounts between organisations (a B2B invoice from an MSP to a company, a licence price in a vendor
  contract, a liability cap), list prices, tariffs and plans that are not tied to a specific person (a price list,
  "the Pro plan costs €12 per month" in a newsletter), budgets, aggregate totals over many people ("payroll cost of
  the IT department"), amounts in legal text ("fines of up to €20 million"), percentages (VAT rate 21%), quantities,
  and ransom demands made of a company. An invoice addressed to a company stays untagged even when a named employee
  is the contact person; an invoice to a sole trader (natural person) is tagged.

### 9.2 JOB_TITLE
- **What is tagged.** A job title, function, role or occupation attributed to a person who is named or otherwise
  identifiable in the document: next to a name ("Piotr Zając, Network Engineer"), in a signature block, email
  footer, org chart, on-call rota, CC list or contact table; in running text when it refers to that specific person
  ("I spoke to your finance controller, Ms Leclercq", "the DPO, who is named above, approved…"); a private
  customer's occupation ("she works as a teacher"); a freelancer's self-description ("freelance web developer").
  Every occurrence is tagged, also a repeated bare role that clearly refers back to the identified person ("the
  sysadmin then reset the account" after the sysadmin was named).
- **Span.** The title as written, including seniority and scope words that belong to it ("Senior DevOps Engineer",
  "Head of IT Operations", "IT-Leiterin", "Kierownik działu IT"); excluding the employer name and linking words
  ("at Larkmead Logistics", "bij", "chez"), honorifics, and a department that is written separately ("IT department"
  in a letterhead). A title and the person's name are separate spans and must not touch.
- **Not tagged.** Generic roles in policies, procedures and templates ("the requester", "administrators must enable
  MFA", "contact the DPO at dpo@…", "Role: [job title]"), process roles with no job meaning ("approver", "ticket
  owner", "assignee", "reporter", "data subject", "customer"), team and department names on their own ("Service
  Desk", "Team Infra"), role mailboxes and group names ("it-admins"), vacancy titles in a job ad with no applicant,
  and job titles of people who are not identifiable (one of "several engineers"). Being a customer, user, employee,
  student or pensioner is not a job title.
- **Conflicts.** A title inside a role mailbox or a username (`dpo@`, `sysadmin01`) is not tagged as JOB_TITLE. A
  title inside an Art. 9/10 phrase belongs to that phrase.

### 9.3 IT identifiers (unchanged rules, restated for IT documents)
- Ticket, change, incident, order, invoice and contract numbers, and asset numbers of servers or unassigned stock, are
  NOT tagged; a customer or account number of a person is CUSTOMER_ID; a staff number or badge number is EMPLOYEE_ID;
  the serial number or asset tag of a laptop, phone, token, loan device or router assigned to a named or identifiable
  person is DEVICE_SERIAL (as in section 3). *(Wording aligned with section 3 at adjudication; v1.4 as first written
  said "asset numbers are NOT tagged" without the qualifier.)*
- Invoice numbers are not tagged, but the customer number on a private customer's invoice is CUSTOMER_ID.

## 10. MED-300 clarifications (v1.5): money amounts and job titles in medical documents
### 10.1 FINANCIAL_AMOUNT in healthcare
- **Tagged** (an identifiable patient, member, participant or staff member pays or receives it): fees and line
  amounts on a patient's invoice or quote (consultation, treatment, a dental crown, IVF, laser surgery), totals,
  deposits, balances due, late fees; prescription charges and co-payments paid by the patient (NHS prescription
  charge, Zuzahlung, ticket modérateur, eigen bijdrage, remgeld, Selbstbehalt); the amount an insurer reimburses
  to a member, the member's remaining share, an annual deductible already used ("eigen risico: €385 van €385
  verbruikt"), an overpayment to be repaid; a trial participant's travel refund or compensation; a staff member's
  salary, allowance, on-call or overtime pay, bank-shift payment and expense refund.
- **Not tagged:** official tariffs and fee schedules on their own (a GOÄ or nomenclature tariff, an NHS charge
  "currently £9.90 per item" in a leaflet), amounts between institutions (hospital-to-insurer invoices, lab price
  lists, a ward budget, a DRG or DBC rate that is not presented as what the patient owes), insurance cover limits
  in policy text, percentages ("reimbursed at 70%"), and amounts in aggregate statistics. When a tariff is printed
  on the patient's own invoice as the line amount, it is that patient's amount and is tagged.
- **Span** as in 9.1: the amount with its currency as written; in a table with the currency in the header, the
  bare number in each cell. A zero amount written as an amount on the patient's document ("€0.00", "0,00 €") is
  tagged like any other; words instead of an amount ("included", "free of charge") are not.

### 10.2 JOB_TITLE in healthcare
- **Tagged:** the job title of an identifiable clinician or staff member ("Consultant in Psychiatry", "Fachärztin
  für Innere Medizin", "verpleegkundig specialist", "pielęgniarka oddziałowa", "Principal Investigator", "Claims
  Handler"), in signatures, letterheads with a named author, rotas, CC lines and introductions; a later bare reference
  that clearly points back to that person ("the consultant reviewed her at 14:00" after Dr X, consultant, was named);
  the patient's or a relative's occupation ("works as an HGV driver", "Beruf: Lehrerin").
- **Span:** the title as written, without the honorific ("Dr", "Prof.", "dr n. med.", "lek."), without the name and
  without the institution or ward ("on Ward 7B", "am Klinikum X"). An honorific or academic degree alone is not a
  job title. A specialty written as part of the title ("consultant cardiologist") is inside the JOB_TITLE span; a
  department name written separately is not tagged (section 8).
- **Not tagged:** generic or process roles that point at no identifiable person ("the responsible clinician",
  "the duty pharmacist", "Prescriber:", "the treating physician must…", "a nurse will call you"), professional
  categories in statistics or policies, and role names inside form labels.
- **Conflicts:** a clinician's title is never HEALTH, also when it reveals the patient's condition ("oncology nurse",
  "psychiatrist"); a clinic name that reveals the condition stays HEALTH as in section 8. An occupation stated as the
  cause of an occupational disease ("baker's asthma", "farmer's lung") is part of the HEALTH span; the occupation
  stated on its own ("Occupation: baker") is JOB_TITLE.

## 11. HR-300 clarifications (v1.6): money amounts and job titles in HR documents
### 11.1 FINANCIAL_AMOUNT in HR
- **Tagged** (an identifiable employee, candidate, leaver or family member is paid it or pays it): annual, monthly and
  hourly salary; a pay rise, bonus, commission, allowance (car, phone, home office, shift, relocation), overtime and
  on-call pay; every line of that person's payslip that is a money amount (basic pay, gross, each tax, social-security,
  pension, union-dues or church-tax deduction, net pay, employer contributions shown on the payslip); expense-claim lines,
  per diems and the amount reimbursed or refused; severance, settlement, pay in lieu of notice, holiday pay, a final
  pay total; an attachment-of-earnings amount, a salary advance or loan, an overpayment to be repaid, a fine or damage
  recharged; a benefit premium or pension contribution of that person; a salary or range offered to a named candidate.
- **Not tagged:** pay scales, salary bands and collective-agreement tables on their own; statutory or company rates
  that are not the person's own amount (minimum wage, mileage rate per km, a tax threshold, a per-diem rate in a
  policy); percentages, hours, days and quantities; budgets, total payroll cost, averages and other aggregate figures;
  fees between companies (a payroll bureau's or law firm's invoice to the employer, an insurer's group premium); a salary
  range in a job advertisement with no applicant. In "212 km × €0.30 = €63.60" only the claimed amount (€63.60) is the
  person's; the rate is not tagged.
- **Span** as in 9.1: the amount with its currency as written; in a payslip or table with the currency in the header,
  the bare number in each cell; a minus sign or brackets that belong to the amount are inside the span.

### 11.2 JOB_TITLE in HR
- **Tagged:** the job title of every identifiable person: the employee concerned, the line manager, the HR contact, a
  colleague or witness, the provider's contact (occupational physician, payroll consultant, employment solicitor); a
  candidate's current and previous titles and the role a named candidate applies for or is offered; the old and new
  title in a promotion or regrading; every later bare reference that clearly points back to that person ("the team
  leader then called him").
- **Span:** the title as written, including seniority and scope ("Senior Payroll Specialist", "stellvertretende
  Filialleiterin", "kierownik magazynu"), without the employer, department, site or grade ("at the Leeds depot",
  "Band 6", "Entgeltgruppe E9", "classe 3"). A grade or pay band is not a job title.
- **Not tagged:** generic and process roles in policies, templates and workflows ("the line manager must…", "Approver:",
  "HR will contact you"), vacancy titles with no applicant, org-chart boxes without a name, department and team names,
  contract types ("fixed-term", "Werkstudent" as a contract status), and statuses that are not jobs ("employee",
  "trainee" without a trade, "pensioner").
- **Conflicts:** a union office (shop steward, délégué syndical, Vertrauensmann der IG Metall) is part of the TRADE_UNION
  phrase (section 7); an elected employee-representative role without a union ("member of the works council",
  "lid van de ondernemingsraad") attributed to a named person is JOB_TITLE. A title inside an email address, username
  or role mailbox is not tagged.


## 12. Danish clarifications (v1.7): IT-360, MED-360 and HR-360
v1.7 adds Danish documents (`it360-da-NNN`, `med360-da-NNN`, `hr360-da-NNN`) to IT-300, MED-300 and HR-300. It
restates the earlier rules for Danish forms and changes no earlier rule.

### 12.1 Identifiers
- **CPR-nummer** (`DDMMÅÅ-XXXX`, also written without the dash) is NATIONAL_ID wherever it appears: on the yellow
  health card (sundhedskort), as the patient identifier in a hospital or GP record, in a payroll file, as the tax
  identifier at SKAT, in an e-Boks or borger.dk header. In medical documents it is NATIONAL_ID, not
  MEDICAL_RECORD_NUMBER, also when it is the only patient identifier.
- **CVR-nummer**, **SE-nummer**, **P-nummer** and the VAT form `DK12345678` are TAX_ID (company registry numbers, as in
  section 3). The "CVR-nr." label stays outside the span.
- **Bank details.** A Danish IBAN (`DK50 0040 0440 1162 43`) is IBAN. The domestic form is the same account and is IBAN
  too: tag registreringsnummer and kontonummer as one span when they are written together (`3409 0001234567`,
  `3409-0001234567`). When they are in two labelled fields ("Reg.nr.: 3409", "Kontonr.: 0001234567"), each value is its
  own IBAN span. A NemKonto statement tags the account in the same way; the word NemKonto is not tagged.
- **Pas, kørekort, nummerplade:** the document number or plate is PASSPORT, DRIVERS_LICENSE or VEHICLE_PLATE
  (`AB 12 345`).
- **MitID and other logins.** A MitID bruger-ID, a NemLog-in or intranet login is USERNAME. The MitID app, a code
  display or a nøglekort as such is not tagged; a one-time code shown to a person is SECRET (section 3).
- **Health and professional numbers.** An authorisation ID from Styrelsen for Patientsikkerhed (autorisations-ID) is
  PROFESSIONAL_ID, and so is a ydernummer when it identifies a single practitioner. A ydernummer of a practice with
  several doctors is a TAX_ID-like organisation number and is not tagged. Hospital case, referral (henvisning),
  requisition and sample numbers are not tagged (section 8).
- **Insurance and pension numbers** (sundhedsforsikring, pensionskasse, ATP is not a number of its own) are
  CUSTOMER_ID; a membership number of a union or an a-kasse is CUSTOMER_ID as well, and the membership itself is
  decided by 12.3.

### 12.2 Names, addresses, phones, dates, amounts
- **Genitive -s.** The Danish genitive is written as one word, so the whole word is tagged ("⟦PERSON|Mettes⟧ bil",
  "⟦PERSON|Lars Tougaards⟧ fravær", "⟦CITY|Aarhus'⟧ havn" with the apostrophe after s-final names). This is the v1.1
  inflected-forms rule.
- **Forms of address and titles.** "hr.", "fru", "frk." and "dr." stay outside the PERSON span. A professional title
  next to a name ("overlæge", "professor", "sygeplejerske") is JOB_TITLE when it describes that person (sections 9, 10,
  11). An academic degree used as a professional designation in a signature ("cand.psych. aut.") is part of the
  JOB_TITLE span; a degree on its own in a CV line is not tagged.
- **Addresses.** Floor and door designations belong to the street address: "Kvædevej 14, 2. th.", "Bystævnet 3, st.
  tv.", "Hyldebærvej 8B, 1. mf." are one STREET_ADDRESS span each. The postcode is four digits (with "DK-" inside the
  span when written together); the postal town is CITY including its district letter or word ("København Ø",
  "Aarhus C", "Odense SV", "Frederiksberg C"). A kommune or region ("Aarhus Kommune", "Region Midtjylland") acting as an
  employer, authority or hospital owner is ORGANISATION; a kommune named as where a person lives ("bor i Gentofte
  Kommune") is CITY on the town part only when it is written as the town ("bor i Gentofte"), otherwise not tagged.
- **Phones.** Danish numbers have 8 digits, usually in pairs (`28 41 66 09`, `+45 28 41 66 09`); the +45 or 0045 prefix
  is inside the span.
- **Dates of birth.** Danish formats (`14.03.1987`, `14-03-1987`, `14. marts 1987`) as in section 3; the first six
  digits of a CPR number are part of the NATIONAL_ID span and are not tagged separately as DATE_OF_BIRTH.
- **Amounts.** Danish amounts are written with a dot for thousands and a comma for decimals; the currency is part of the
  span in whichever form is written: `12.500,00 kr.`, `kr. 3.450`, `DKK 1.250,50`, `450,-` (the ",-" belongs to the
  amount). Section 9.1, 10.1 and 11.1 decide which amounts are tagged. Danish statutory figures on their own are not
  tagged: the AM-bidrag rate (8 %), ATP rates, the befordringsfradrag rate per km, the official mileage rate
  (statens takst), personfradrag, beskæftigelsesfradrag and the sygedagpenge ceiling. The person's own AM-bidrag,
  A-skat, ATP, pension, feriepenge and fagforeningskontingent amounts on a payslip are tagged.

### 12.3 Special categories (Art. 9 and 10) in Danish documents
- **HEALTH:** "sygemeldt" and "syg" about a person, a "lægeerklæring" or "friattest" with a content, a "§ 56-aftale"
  (agreement under sygedagpengeloven for a chronic or long-term illness) stated about a person, "fleksjob" and
  "førtidspension" when stated as the person's status (they reveal reduced working capacity for health reasons), a
  "mulighedserklæring" with its content, "arbejdsskade" with the injury. The law name itself, a form name without
  content, and "barsel" (parental leave) without a health detail are not tagged; "graviditetsbetinget fravær" is.
- **RELIGION_BELIEF:** membership of the folkekirke or another faith recorded for a person ("medlem af folkekirken",
  "udmeldt af folkekirken"). On a payslip or tax card, the person's kirkeskat line states membership: the amount is
  FINANCIAL_AMOUNT (12.2) and the label is not tagged, except where it is written as a statement ("betaler kirkeskat",
  "kirkeskat: ja"), which is RELIGION_BELIEF. The kirkeskat rate of a kommune is not tagged.
- **TRADE_UNION:** membership of or an office in a fagforening (3F, HK, Dansk Metal, FOA, DSR, Djøf, IDA, Krifa and so on)
  stated about a person, union dues (fagforeningskontingent) deducted from a person's pay, and the tillidsrepræsentant
  (shop steward) role, which is a union office (section 11.2). Membership of an a-kasse alone is unemployment insurance
  and is NOT TRADE_UNION, also when the a-kasse carries a union's name; it becomes TRADE_UNION only where the text
  states union membership as well. A union named as a party to an overenskomst is ORGANISATION. A
  sikkerhedsrepræsentant (safety representative) is JOB_TITLE when attributed to a named person.
- **CRIMINAL_OFFENCE:** the content of a straffeattest or børneattest (a clean "ren straffeattest" or "børneattesten
  er uden anmærkninger" too), a police report, a charge (sigtelse, tiltale), a conviction or a fine for an offence
  (bødeforlæg for spirituskørsel) of an identifiable person. Asking for an attest without a result is not tagged.
- **ETHNIC_ORIGIN, POLITICAL_OPINION, GENETIC, BIOMETRIC, SEX_LIFE_ORIENTATION** follow sections 3, 7 and 8 unchanged
  ("efterkommer af tyrkiske indvandrere" is ETHNIC_ORIGIN; statsborgerskab, opholdstilladelse and the language a
  person speaks are not; a seat on the kommunalbestyrelse for a party is POLITICAL_OPINION).
