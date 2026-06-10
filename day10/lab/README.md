# Lab Day 10 - Data Pipeline & Data Observability

Repo nay chua pipeline cho bai lab Day 10 theo flow:

`raw CSV -> clean -> validate -> publish -> eval -> grading -> freshness`

Pipeline da duoc sua de:

- clean dung 5 nguon chinh thuc
- loai bo stale HR content
- sua refund window `14 -> 7 ngay lam viec`
- quarantine duplicate, missing field, noisy text
- grading chay end-to-end ngay ca khi Chroma local loi

---

## 1. Cau truc chinh

| File | Vai tro |
|---|---|
| `etl_pipeline.py` | Chay pipeline ingest -> clean -> validate -> publish |
| `transform/cleaning_rules.py` | Cac cleaning rule va quarantine rule |
| `quality/expectations.py` | Expectation suite sau clean |
| `retrieval_backend.py` | Chon Chroma hoac fallback retrieval tu cleaned CSV |
| `eval_retrieval.py` | Eval retrieval tren bo `test_questions.json` |
| `grading_run.py` | Chay grading chinh thuc tren `grading_questions.json` |

---

## 2. Cai dat moi truong

### Windows PowerShell

```powershell
cd day10\lab
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

Neu muon chay truc tiep khong activate:

```powershell
.\venv\Scripts\python.exe --version
```

---

## 3. Chay pipeline

### Lan dau de quan sat loi baseline

```powershell
.\venv\Scripts\python.exe etl_pipeline.py run
```

Ban goc se HALT neu expectation fail. Day la hanh vi dung cua bai lab.

### Run chuan sau khi da sua

```powershell
.\venv\Scripts\python.exe etl_pipeline.py run --run-id codex-fix-2026-06-10d
```

Run thanh cong se tao:

- `artifacts/cleaned/cleaned_codex-fix-2026-06-10d.csv`
- `artifacts/quarantine/quarantine_codex-fix-2026-06-10d.csv`
- `artifacts/manifests/manifest_codex-fix-2026-06-10d.json`
- `artifacts/logs/run_codex-fix-2026-06-10d.log`

Run tot mong doi:

- `raw_records=247`
- `cleaned_records=37`
- `quarantine_records=210`
- tat ca halt expectations pass
- log co `PIPELINE_OK`

---

## 4. Cac cleaning rule dang ap dung

Pipeline hien tai giu 5 `doc_id` chinh thuc:

- `policy_refund_v4`
- `sla_p1_2026`
- `it_helpdesk_faq`
- `hr_leave_policy`
- `access_control_sop`

Record se bi quarantine neu:

- `doc_id` khong nam trong allowlist
- `effective_date` rong hoac sai format
- `hr_leave_policy` co `effective_date < 2026-01-01`
- `chunk_text` rong
- chunk chi chua noise sau khi strip prefix `Noi dung khong ro rang:`
- chunk lap mot cau tu 3 lan tro len
- chunk HR van chua noi dung stale `10 ngay phep nam` hoac `ban HR 2025`
- chunk bi trung noi dung voi chunk da duoc giu

Rule sua noi dung:

- `policy_refund_v4`: thay `14 ngay lam viec` bang `7 ngay lam viec`

---

## 5. Expectation suite

Expectation hien tai:

- `min_one_row` - halt
- `no_empty_doc_id` - halt
- `refund_no_stale_14d_window` - halt
- `chunk_min_length_8` - warn
- `effective_date_iso_yyyy_mm_dd` - halt
- `hr_leave_no_stale_10d_annual` - halt
- `required_doc_coverage` - halt
- `no_repeated_sentence_burst` - warn

Pipeline se dung neu co expectation `halt` nao fail.

---

## 6. Eval retrieval

Chay bo test tu kiem:

```powershell
.\venv\Scripts\python.exe eval_retrieval.py --out artifacts/eval/eval_after_fix.csv
```

File output:

- `artifacts/eval/eval_after_fix.csv`

Can kiem tra:

- `contains_expected=yes`
- `hits_forbidden=no`
- `top1_doc_expected=yes` voi cac cau co quy dinh source

---

## 7. Grading chinh thuc

```powershell
.\venv\Scripts\python.exe grading_run.py --out artifacts/eval/grading_run.jsonl
```

File output:

- `artifacts/eval/grading_run.jsonl`

Ket qua mong doi:

- 10/10 cau `contains_expected=true`
- 10/10 cau `hits_forbidden=false`
- 10/10 cau `top1_doc_matches=true`

---

## 8. Freshness check

```powershell
.\venv\Scripts\python.exe etl_pipeline.py freshness --manifest artifacts/manifests/manifest_codex-fix-2026-06-10d.json
```

`freshness_check=FAIL` trong run hien tai la mong doi, vi:

- `latest_exported_at = 2026-04-10T00:00:00`
- SLA mac dinh = `24h`
- du lieu qua cu so voi nguong monitoring

Day la signal dung cua bai monitoring, khong phai bug pipeline.

---

## 9. Fallback retrieval khi Chroma loi

Moi truong local hien tai co the gap:

- `disk I/O error`
- Chroma khong mo duoc `PersistentClient`

Pipeline da duoc sua de fallback:

- `etl_pipeline.py` van publish cleaned snapshot
- `eval_retrieval.py` va `grading_run.py` se dung `retrieval_backend.py`
- neu Chroma loi, he thong truy van cleaned CSV moi nhat bang keyword scoring

Dieu nay giup bai lab van chay end-to-end va grading van sinh artifact hop le.

---

## 10. Kich ban inject corruption

Dung de tao before/after evidence:

```powershell
.\venv\Scripts\python.exe etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
.\venv\Scripts\python.exe eval_retrieval.py --out artifacts/eval/after_inject_bad.csv
.\venv\Scripts\python.exe etl_pipeline.py run --run-id codex-fix-2026-06-10d
.\venv\Scripts\python.exe eval_retrieval.py --out artifacts/eval/eval_after_fix.csv
```

So sanh:

- `after_inject_bad.csv`
- `eval_after_fix.csv`

Muc tieu la chung minh retrieval te hon truoc fix va tot hon sau fix.

---

## 11. Artifact quan trong

| Artifact | Y nghia |
|---|---|
| `artifacts/cleaned/*.csv` | Du lieu da clean de publish |
| `artifacts/quarantine/*.csv` | Du lieu bi loai kem ly do |
| `artifacts/logs/*.log` | Log chi tiet tung run |
| `artifacts/manifests/*.json` | Manifest cua run va freshness metadata |
| `artifacts/eval/*.csv` | Ket qua eval retrieval |
| `artifacts/eval/grading_run.jsonl` | Ket qua grading chinh thuc |

---

## 12. Lenh chay nhanh de nop bai

```powershell
cd day10\lab
.\venv\Scripts\python.exe etl_pipeline.py run --run-id codex-fix-2026-06-10d
.\venv\Scripts\python.exe eval_retrieval.py --out artifacts/eval/eval_after_fix.csv
.\venv\Scripts\python.exe grading_run.py --out artifacts/eval/grading_run.jsonl
.\venv\Scripts\python.exe etl_pipeline.py freshness --manifest artifacts/manifests/manifest_codex-fix-2026-06-10d.json
```
