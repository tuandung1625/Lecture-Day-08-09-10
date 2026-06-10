# Bao Cao Nhom - Lab Day 10: Data Pipeline & Data Observability

**Ten:** Nguyen Tuan Dung - 2A202600848  
**Ngay nop:** 2026-06-10  
**Repo:** `day10/lab`

---

## 1. Pipeline tong quan

Pipeline cua nhom xu ly du lieu raw tu file `data/raw/policy_export_dirty.csv`, sau do di qua cac buoc ingest -> clean -> validate -> publish -> eval. Muc tieu cua pipeline la dua du lieu sach vao retrieval layer de tra loi dung cho bo cau hoi grading va dong thoi giu lai day du bang chung ve quarantine, expectation, manifest va freshness.

Trong lan chay dau, pipeline HALT vi expectation `hr_leave_no_stale_10d_annual` phat hien van con du lieu HR stale trong tap cleaned. Sau khi doi chieu raw CSV, allowlist va `grading_questions.json`, nhom xac dinh duoc hai van de goc: `access_control_sop` bi bo sot khoi allowlist, va chunk HR 2025 bi gan nham `effective_date` nam 2026 nen vuot qua bo loc cu. Pipeline duoc sua de xu ly dung ca hai truong hop nay, dong thoi bo sung them cleaning rule cho noisy text va repetitive text.

`run_id` duoc lay tu log va manifest. Run chinh sau khi sua thanh cong la `codex-fix-2026-06-10d`, sinh ra cleaned CSV, quarantine CSV, manifest va cac artifact eval/grading.

**Lenh chay mot dong:**

```powershell
.\venv\Scripts\python.exe etl_pipeline.py run --run-id codex-fix-2026-06-10d
```

---

## 2. Cleaning & expectation

Baseline ban dau da co nhung rule co ban nhu allowlist, chuan hoa `effective_date`, loai bo HR stale theo ngay, dedupe va refund fix `14 -> 7 ngay lam viec`. Tuy nhien baseline chua du chat vi stale HR content van co the lot qua cleaned neu `effective_date` bi gan moi hon thuc te. Nhom da them 4 thay doi co tac dong ro rang: bo sung `access_control_sop` vao allowlist, strip noisy prefix, quarantine chunk lap cau bat thuong, va quarantine stale HR theo noi dung thay vi chi theo ngay.

O lop expectation, nhom giu cac expectation cu va them 2 expectation moi: `required_doc_coverage` de dam bao cleaned van con du 5 nguon chinh thuc, va `no_repeated_sentence_burst` de canh bao chunk co mau export loi. Cac expectation `halt` la: `min_one_row`, `no_empty_doc_id`, `refund_no_stale_14d_window`, `effective_date_iso_yyyy_mm_dd`, `hr_leave_no_stale_10d_annual`, va `required_doc_coverage`.

### 2a. Bang metric_impact

| Rule / Expectation moi | Truoc | Sau | Chung cu |
|---|---:|---:|---|
| Them `access_control_sop` vao allowlist | 8 row bi quarantine nham | 8 row duoc dua vao cleaned / dedupe hop le | `grading_run.jsonl`, `gq_d10_10` pass |
| `stale_hr_policy_text` | 2 violation expectation HR stale | 0 violation | log `run_codex-fix-2026-06-10d.log` |
| `repeated_sentence_burst` | chunk lap cau lot vao cleaned | 2 row bi quarantine | `quarantine_codex-fix-2026-06-10d.csv` |
| `required_doc_coverage` | khong co gate coverage | `missing=[]` | log run thanh cong |
| `no_repeated_sentence_burst` | khong co canh bao | `violations=0` sau clean | log run thanh cong |

**Rule chinh (baseline + mo rong):**

- Allowlist 5 `doc_id` chinh thuc: refund, SLA, FAQ, HR, access control.
- Chuan hoa `effective_date` ve ISO `YYYY-MM-DD`.
- Quarantine `hr_leave_policy` neu `effective_date < 2026-01-01`.
- Quarantine neu `chunk_text` rong hoac `effective_date` thieu.
- Strip prefix noise `Noi dung khong ro rang:`.
- Quarantine chunk lap mot cau tu 3 lan tro len.
- Quarantine stale HR theo noi dung `10 ngay phep nam` / `ban HR 2025`.
- Dedupe theo normalized chunk text.
- Sua stale refund text `14 ngay lam viec` thanh `7 ngay lam viec`.

**Vi du 1 lan expectation fail va cach xu ly:**

Expectation `hr_leave_no_stale_10d_annual` fail trong lan chay dau vi cleaned van con chunk HR noi `10 ngay phep nam`. Nhom da bo sung rule `stale_hr_policy_text` trong `cleaning_rules.py`, dung normalize text khong dau de bat ca truong hop chunk HR 2025 bi gan nham `effective_date` nam 2026. Sau khi sua, expectation nay pass voi `violations=0`.

---

## 3. Before / after anh huong retrieval hoac agent

Truoc khi sua, retrieval co nguy co tra ve context sai o hai nhom cau hoi: nhom refund co the cham chunk stale `14 ngay lam viec`, va nhom HR co the cham chunk `10 ngay phep nam` duoc gan date 2026. Ca hai truong hop deu rat nguy hiem vi cau tra loi co the nhin hop ly nhung context thuc te da stale.

Kich ban before/after duoc quan sat qua hai mốc:
- Before: pipeline HALT o expectation HR stale, chung to cleaned chua dat chat luong publish.
- After: pipeline pass toan bo expectation halt, sau do eval va grading deu chay thanh cong.

Do moi truong cuc bo gap `Chroma disk I/O error`, nhom bo sung fallback retrieval tu cleaned CSV de giu duoc kha nang eval/grading end-to-end. Fallback nay van dam bao keyword match, number match va top-1 doc source cho grading. Ket qua thuc te cho thay `grading_run.jsonl` dat 10/10 cau voi `contains_expected=true`, `hits_forbidden=false`, `top1_doc_matches=true`.

**Kich ban inject:**

```powershell
.\venv\Scripts\python.exe etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
.\venv\Scripts\python.exe eval_retrieval.py --out artifacts/eval/after_inject_bad.csv
```

Khi inject, expectation refund se fail neu khong bo qua validate, va retrieval co the hit forbidden text `14 ngay`. Sau khi chay lai pipeline chuan, file `artifacts/eval/eval_after_fix.csv` cho thay cac cau hoi refund va HR deu dung context moi.

**Ket qua dinh luong:**

- `raw_records = 247`
- `cleaned_records = 37`
- `quarantine_records = 210`
- `grading_run.jsonl`: 10/10 cau pass
- `eval_after_fix.csv`: tat ca dong `contains_expected=yes`, `hits_forbidden=no`

---

## 4. Freshness & monitoring

Manifest run chinh la `artifacts/manifests/manifest_codex-fix-2026-06-10d.json`. Trong run nay, `freshness_check=FAIL` vi `latest_exported_at = 2026-04-10T00:00:00`, trong khi SLA cau hinh la 24 gio. Nghia la du lieu da qua cu so voi nguong monitoring, nen pipeline ghi nhan tinh trang stale o tang quan sat.

Y nghia PASS/WARN/FAIL:
- PASS: du lieu moi hon hoac bang SLA.
- WARN: co dau hieu can theo doi gan nguong SLA.
- FAIL: vuot qua nguong SLA, can canh bao van hanh.

Trong bai lab nay, freshness FAIL la ket qua mong doi cua phan monitoring, vi muc tieu khong phai lam cho manifest luon xanh, ma la hieu va giai thich dung y nghia cua freshness signal.

---

## 5. Lien he Day 09

Du lieu sau clean va publish phuc vu truc tiep cho retrieval layer cua Day 09, vi cung xoay quanh case CS + IT Helpdesk. Khac biet la Day 10 tap trung vao tang data reliability truoc khi agent doc du lieu. Sau khi sua pipeline, cleaned snapshot hoac collection publish se cung cap context dung version cho agent, tranh truong hop agent tra loi sai do stale policy.

---

## 6. Rui ro con lai & viec chua lam

- Chroma local dang gap `disk I/O error`, nen run hien tai dang publish qua `local_csv_fallback` thay vi vector backend chuan.
- Fallback retrieval du de pass grading keyword-based, nhung khong thay the semantic retrieval that su.
- Chua bo sung day du evidence `after_inject_bad.csv` vao artifact de hoan tat Sprint 3 theo huong before/after.
- Chua dien het cac file docs phu tro nhu `docs/runbook.md`, `docs/data_contract.md`, `docs/pipeline_architecture.md`.
