# Ideal customer profile

> One Fit section per market. `scripts/score.py` scores fit against the account's own market section;
> `scripts/resolve.py` uses the same `fit:` block to decide `new_lead` vs `dropped`.
> Each section's fenced yaml block is machine-read: keep its keys and terms (ontology industries only).

## Fit — Singapore (SG)
Multi-site or growing SMBs in F&B, retail (including single and multi-outlet shops), logistics,
professional services, clinics and education, 10–200 staff, anywhere in Singapore. No prerequisites.
```yaml
fit:
  industries: [fnb, retail, logistics, professional_services, clinics, education]
  employees: [10, 200]
  regions: []          # empty = whole market
  ssic_prefixes:       # ACRA primary SSIC code prefix -> industry
    fnb: ["56"]
    retail: ["47"]
    logistics: ["49", "52", "53"]           # land transport, warehousing, couriers (not sea/air: 50, 51)
    professional_services: ["69", "71", "73"]   # not 70: head offices / management consultancy (shells)
    clinics: ["86"]
    education: ["85"]
```

## Fit — Malaysia (MY)
Same industries and size band as Singapore; Klang Valley, Penang and Johor first. Not live yet: refine
before switching MY on.
```yaml
fit:
  industries: [fnb, retail, logistics, professional_services, clinics, education]
  employees: [10, 200]
  regions: [Kuala Lumpur, Selangor, Petaling Jaya, Shah Alam, Penang, George Town, Johor, Johor Bahru]
```

## Fit — India (IN)
Same industries and size band; Bengaluru, Mumbai, Delhi NCR and Chennai only. Not live yet (ADR-0005:
no real Indian data until the DPDP approach is signed off); keep this tight when it goes live.
```yaml
fit:
  industries: [fnb, retail, logistics, professional_services, clinics, education]
  employees: [10, 200]
  regions: [Bengaluru, Bangalore, Mumbai, Delhi, New Delhi, Gurugram, Gurgaon, Noida, Chennai]
```

## Hard exclusions
- Government agencies, ministries, statutory boards and town councils.
- Telcos and IT managed-service providers (competitors).
- Sole proprietors and one-person businesses (also keeps registry data away from individuals).
- Large enterprises: listed companies or more than 500 staff.
```yaml
exclude:
  max_employees: 500
  entity_types: [sole proprietorship, sole-proprietor, sole proprietor, partnership]
  name_patterns: ["ministry", "authority", "town council", "statutory board", "government",
                  "telecom", "telco", "singtel", "starhub", "m1 limited", "managed services",
                  "it services", "it solutions", "limited \\(listed\\)"]
```
