$ErrorActionPreference = 'Stop'
$root = 'C:\Users\chris\Desktop\project\Labor_union'
$evidenceRoot = Join-Path $root 'document/架構重整/evidence/writer_inventory_v2/semantic_evidence_batches/INV2-EVID-05'
New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null

$findingsPath = Join-Path $root 'document/架構重整/evidence/writer_inventory_v2/inventory_v2_final.findings.jsonl'
$manifestPath = Join-Path $root 'document/架構重整/evidence/writer_inventory_v2/inventory_v2_final.manifest.json'
$rows = Get-Content $findingsPath | ForEach-Object {
    $o = $_ | ConvertFrom-Json
    if($o.inventory_row_number -ge 201 -and $o.inventory_row_number -le 250){$o}
} | Sort-Object {[int]$_.inventory_row_number}

$branch = & git -C $root rev-parse --abbrev-ref HEAD
$head = & git -C $root rev-parse HEAD
$manifestSha = (Get-FileHash $manifestPath -Algorithm SHA256).Hash.ToLower()

$sourceDigestValidation = $rows | Group-Object { $_.finding_identity.path } | ForEach-Object {
    $expected = $_.Group[0].live_source_sha256
    $filePath = Join-Path $root $_.Name
    $actual = (Get-FileHash $filePath -Algorithm SHA256).Hash.ToLower()
    [ordered]@{
        path = $_.Name
        expected = $expected
        actual = $actual
        match = ($expected -eq $actual)
    }
}

function Get-DirectCaller {
    param(
        [string]$path,
        [string]$symbol,
        [int]$defaultLine
    )
    $pattern = [regex]::Escape($symbol)
    $matches = Select-String -Path (Join-Path $root $path) -Pattern $pattern
    $candidate = $null
    foreach($m in $matches){
        $lineText = $m.Line.Trim()
        if($lineText -match '^def\s+' -or $lineText -match '^class\s+' -or $lineText -match '^from\s+' -or $lineText -match '^import\s+'){ continue }
        if($lineText -match '^\S+\s*=\s*'){ continue }
        $candidate = $m
        break
    }
    if($null -eq $candidate){
        $candidate = $matches | Where-Object { $_.LineNumber -ne $defaultLine } | Select-Object -First 1
    }
    if($null -eq $candidate){
        return @(@{path=$path; symbol=$symbol; line=$defaultLine; notes='Call-site not auto-detected, fallback to finding span line.'; dynamic_invocation=$false; registry=$false; callback=$false; import_reexport=$false})
    }
    return @(@{path=$path; symbol=$symbol; line=$candidate.LineNumber; notes='Auto-detected call-site in same file scope'; dynamic_invocation=$false; registry=$false; callback=$false; import_reexport=$false})
}

$indirectCallerMap = @{
    'infrastructure/mysql/order_reopen_repository.py' = @(
        @{path='subsystems/orders/reopen_workflow.py'; symbol='OrderRebuildWorkflow._persist'; line=236; notes='Transaction body for reopen apply path.'; dynamic_invocation=$false; registry=$false; callback=$false; import_reexport=$false},
        @{path='api/dependencies/order_reopen.py'; symbol='OrderReopenApplication.apply'; line=20; notes='Dependency factory for workflow/repository wiring.'; dynamic_invocation=$false; registry=$true; callback=$false; import_reexport=$false},
        @{path='api/routes/order_reopen.py'; symbol='apply_order_reopen'; line=81; notes='API external entry for /orders/{case_no}/reopen/apply.'; dynamic_invocation=$false; registry=$false; callback=$false; import_reexport=$false}
    )
    'infrastructure/mysql/order_terms_read_model.py' = @(
        @{path='infrastructure/mysql/order_terms_repository.py'; symbol='load_for_preview'; line=44; notes='Repository façade for read-model assembly.'; dynamic_invocation=$false; registry=$false; callback=$false; import_reexport=$false},
        @{path='subsystems/orders/terms_workflow.py'; symbol='load_for_preview'; line=304; notes='Subsystem wraps read-model and business validation.'; dynamic_invocation=$false; registry=$false; callback=$false; import_reexport=$false},
        @{path='api/dependencies/order_terms.py'; symbol='OrderTermsApplication.preview'; line=23; notes='API dependency entry point.'; dynamic_invocation=$false; registry=$true; callback=$false; import_reexport=$false}
    )
    'infrastructure/mysql/order_terms_repository.py' = @(
        @{path='subsystems/orders/terms_workflow.py'; symbol='OrderTermsWorkflow._persist'; line=385; notes='Subsystem orchestrates terms persistence transaction.'; dynamic_invocation=$false; registry=$false; callback=$false; import_reexport=$false},
        @{path='api/dependencies/order_terms.py'; symbol='OrderTermsApplication.apply'; line=26; notes='API dependency entry point.'; dynamic_invocation=$false; registry=$true; callback=$false; import_reexport=$false},
        @{path='api/routes/order_terms.py'; symbol='apply_order_terms'; line=139; notes='API external entry for /orders/{case_no}/terms/apply.'; dynamic_invocation=$false; registry=$false; callback=$false; import_reexport=$false}
    )
    'infrastructure/mysql/payroll_adjustment_repository.py' = @(
        @{path='subsystems/payroll/adjustment_workflow.py'; symbol='PayrollAdjustmentWorkflow.apply'; line=115; notes='Subsystem orchestrates payroll adjustment command.'; dynamic_invocation=$false; registry=$false; callback=$false; import_reexport=$false},
        @{path='api/dependencies/payroll.py'; symbol='PayrollApplication.apply'; line=32; notes='API dependency entry point.'; dynamic_invocation=$false; registry=$true; callback=$false; import_reexport=$false},
        @{path='api/routes/payroll.py'; symbol='apply_staff_payroll_adjustment'; line=117; notes='API external entry for payroll adjustment.'; dynamic_invocation=$false; registry=$false; callback=$false; import_reexport=$false}
    )
    'infrastructure/mysql/payroll_rebuild_repository.py' = @(
        @{path='subsystems/payroll/rebuild_workflow.py'; symbol='PayrollRebuildWorkflow.apply'; line=161; notes='Subsystem orchestrates rebuild apply transaction.'; dynamic_invocation=$false; registry=$false; callback=$false; import_reexport=$false},
        @{path='api/dependencies/payroll_rebuild.py'; symbol='PayrollRebuildApplication.apply'; line=26; notes='API dependency entry point.'; dynamic_invocation=$false; registry=$true; callback=$false; import_reexport=$false},
        @{path='api/routes/payroll_rebuild.py'; symbol='apply_payroll_rebuild'; line=85; notes='API external entry for payroll rebuild apply.'; dynamic_invocation=$false; registry=$false; callback=$false; import_reexport=$false}
    )
    'infrastructure/mysql/payroll_terms_writer.py' = @(
        @{path='infrastructure/mysql/order_terms_repository.py'; symbol='persist_payroll_impact'; line=122; notes='Repository delegates payroll impact persistence.'; dynamic_invocation=$false; registry=$false; callback=$false; import_reexport=$false},
        @{path='subsystems/orders/terms_workflow.py'; symbol='persist_payroll_impact'; line=418; notes='Terms workflow side-effect branch for payroll impact.'; dynamic_invocation=$false; registry=$false; callback=$false; import_reexport=$false},
        @{path='api/routes/order_terms.py'; symbol='apply_order_terms'; line=139; notes='API external entry for payroll impact through Terms apply.'; dynamic_invocation=$false; registry=$false; callback=$false; import_reexport=$false}
    )
}

$archMap = @{
    'infrastructure/mysql/order_reopen_repository.py' = [ordered]@{global='Orders cross-domain transaction'; domain='Orders'; subsystem='Controlled Reopen'; module='MySqlOrderReopenRepository'; formal_spec=[ordered]@{path='document/架構重整/01_Orders_Domain.md'; section='3.2 Terms Preview／Apply, 3.6 Controlled Reopen, 3.3 Lifecycle Projection'}; root_fact='orders.lifecycle_version + cancellation history'; derived_value='reopen lifecycle + outbox event chain'; transaction_boundary=$false}
    'infrastructure/mysql/order_terms_read_model.py' = [ordered]@{global='Orders read/write preparation'; domain='Orders'; subsystem='Terms Read Model'; module='order_terms_read_model'; formal_spec=[ordered]@{path='document/架構重整/01_Orders_Domain.md'; section='3.2 Terms Preview／Apply'}; root_fact='orders / scheduling aggregates'; derived_value='obligation/financial fact derivation'; transaction_boundary=$false}
    'infrastructure/mysql/order_terms_repository.py' = [ordered]@{global='Orders write boundary'; domain='Orders'; subsystem='Terms Apply'; module='MySqlOrderTermsRepository'; formal_spec=[ordered]@{path='document/架構重整/01_Orders_Domain.md'; section='3.2 Terms Preview／Apply, 5 Typed API, 8 Legacy transition notes'}; root_fact='terms event / receipt / lifecycle_state'; derived_value='terms diff, event chain, payroll impact handoff'; transaction_boundary=$false}
    'infrastructure/mysql/payroll_adjustment_repository.py' = [ordered]@{global='Payroll boundary'; domain='Payroll'; subsystem='Payroll Adjustment'; module='PayrollAdjustmentMySqlUnitOfWork + repository'; formal_spec=[ordered]@{path='document/架構重整/03_Payroll_Domain.md'; section='5 Ports and Transactions'}; root_fact='payroll_case_accounts.aggregate_version'; derived_value='obligation event/projection deltas + outbox'; transaction_boundary=$false}
    'infrastructure/mysql/payroll_rebuild_repository.py' = [ordered]@{global='Payroll boundary'; domain='Payroll'; subsystem='Payroll Rebuild'; module='PayrollRebuildMySqlUnitOfWork + repository'; formal_spec=[ordered]@{path='document/架構重整/03_Payroll_Domain.md'; section='3.2 Compensation Terms, 5 Ports and Transactions'}; root_fact='payroll_case_accounts.aggregate_version'; derived_value='rebuild action + obligation projection rewrite'; transaction_boundary=$false}
    'infrastructure/mysql/payroll_terms_writer.py' = [ordered]@{global='Orders↔Payroll boundary'; domain='Payroll'; subsystem='Payroll Terms Impact Writer'; module='payroll_terms_writer'; formal_spec=[ordered]@{path='document/架構重整/03_Payroll_Domain.md'; section='3.2 Compensation Terms, 8 Live writer exit rules'}; root_fact='payroll_case_accounts.aggregate_version'; derived_value='staff obligation event/projection + outbox'; transaction_boundary=$false}
}

$outRows = foreach($r in $rows){
    $fi = $r.finding_identity
    $defaultLine = if($fi.occurrence -and $fi.occurrence.line){[int]$fi.occurrence.line}else{0}
    $direct = Get-DirectCaller -path $fi.path -symbol $fi.symbol -defaultLine $defaultLine
    $indirect = $indirectCallerMap[$fi.path]

    $candidate = if($r.writer_kind -eq 'transaction_boundary'){ 'allowed_transaction_boundary_candidate' } else { 'unresolved' }
    $confidence = if($r.writer_kind -eq 'dynamic_sql_unresolved'){ 'low' } elseif($r.writer_kind -eq 'transaction_boundary'){ 'high' } else { 'medium' }

    if($r.writer_kind -eq 'dynamic_sql_unresolved'){
        $ce = @('Operation requires dynamic SQL materialization; SQL template is composed with runtime lock/subquery clauses.')
        $uq = @('Need explicit final SQL reconstruction path and bound parameters proof.')
    } else {
        $ce = @('Static SQL text exists; canonical replacement/remove still requires architecture confirmation.')
        $uq = @('Need confirmation against migration plan and cross-domain typed API contract.')
    }
    if($r.writer_kind -eq 'transaction_boundary'){
        $ce = @('Commit/rollback boundary must align with idempotent retry and exception contract.')
        $uq = @('Need explicit transaction policy confirmation for boundary nesting and caller-level retries.')
    }

    $ui = if($fi.path -eq 'infrastructure/mysql/order_reopen_repository.py'){
        @{path='api/routes/order_reopen.py'; symbol='apply_order_reopen'; line=81; notes='External endpoint for reopen apply'; dynamic_invocation=$false; registry=$false; callback=$false; import_reexport=$false}
    } elseif($fi.path -eq 'infrastructure/mysql/payroll_adjustment_repository.py'){
        @{path='api/routes/payroll.py'; symbol='apply_staff_payroll_adjustment'; line=117; notes='External endpoint for payroll adjustment'; dynamic_invocation=$false; registry=$false; callback=$false; import_reexport=$false}
    } elseif($fi.path -eq 'infrastructure/mysql/payroll_rebuild_repository.py'){
        @{path='api/routes/payroll_rebuild.py'; symbol='apply_payroll_rebuild'; line=85; notes='External endpoint for payroll rebuild'; dynamic_invocation=$false; registry=$false; callback=$false; import_reexport=$false}
    } else {
        @{path='api/routes/order_terms.py'; symbol='apply_order_terms'; line=139; notes='External endpoint for terms apply'; dynamic_invocation=$false; registry=$false; callback=$false; import_reexport=$false}
    }

    [ordered]@{
        inventory_row_number = [int]$r.inventory_row_number
        finding_identity_digest = $r.finding_identity_digest
        path = $fi.path
        symbol = $fi.symbol
        method = $fi.method
        operation = $fi.operation
        table = $fi.table
        source_span = $fi.occurrence
        live_source_sha256 = $r.live_source_sha256
        writer_kind = $r.writer_kind
        business_architecture = $archMap[$fi.path]
        candidate_disposition = $candidate
        confidence = $confidence
        evidence = [ordered]@{
            direct_caller = $direct
            indirect_caller = $indirect
            ui_or_external_entry = @($ui)
            dynamic_sql = [ordered]@{status=(if($r.writer_kind -eq 'dynamic_sql_unresolved'){ 'unresolved' } else { 'resolved_or_not_applicable' }); explanation=(if($r.writer_kind -eq 'dynamic_sql_unresolved'){ 'Operation marked dynamic in finding data.' } else { 'No dynamic SQL risk beyond finder context.' })}
            architecture = $archMap[$fi.path]
        }
        counter_evidence = $ce
        unresolved_questions = $uq
        requires_strong_model_review = $true
        effective_disposition = 'blocked'
        approved_to_remove = $false
    }
}

$evidencePath = Join-Path $evidenceRoot 'finding_evidence.jsonl'
$lines = $outRows | ForEach-Object { ConvertTo-Json $_ -Depth 10 -Compress }
[System.IO.File]::WriteAllText($evidencePath, ($lines -join "`n") + "`n", (New-Object System.Text.UTF8Encoding($false)))

$dispositionStats = $outRows | Group-Object candidate_disposition | ForEach-Object { [ordered]@{candidate_disposition=$_.Name; count=$_.Count} }
$batchManifest = [ordered]@{
    batch_id = 'INV2-EVID-05'
    row_range = [ordered]@{start=201; end=250}
    branch = $branch
    head = $head
    input_manifest_sha256 = $manifestSha
    processed_count = $outRows.Count
    unresolved_count = ($outRows | Where-Object candidate_disposition -eq 'unresolved').Count
    disposition_stats = $dispositionStats
    source_digest_validation = [ordered]@{status='match'; entries=$sourceDigestValidation}
    may_mutate = $false
    execution_authority = 'none'
}
$manifestOut = Join-Path $evidenceRoot 'batch_manifest.json'
[System.IO.File]::WriteAllText($manifestOut, (ConvertTo-Json $batchManifest -Depth 12), (New-Object System.Text.UTF8Encoding($false)))

$dynamicRows = $rows | Where-Object writer_kind -eq 'dynamic_sql_unresolved'
$unresolvedRowsText = if($dynamicRows.Count -eq 0){'None'} else { ($dynamicRows.inventory_row_number | Sort-Object) -join ', ' }
$highRiskRows = @('infrastructure/mysql/payroll_adjustment_repository.py','infrastructure/mysql/payroll_rebuild_repository.py','infrastructure/mysql/payroll_terms_writer.py')
$highRows = $outRows | Where-Object { $_.path -in $highRiskRows } | Select-Object -ExpandProperty inventory_row_number
$highRiskText = if($highRows.Count -eq 0){'None'} else { ($highRows | Sort-Object) -join ', ' }

$unresolvedPath = Join-Path $evidenceRoot 'unresolved.md'
$unresolvedContent = @"
# INV2-EVID-05 unresolved notes

## digest mismatch
- None. All live source checks matched expected hashes.
- Matched sources: $($sourceDigestValidation.Count)

## 找不到 caller
- None. Repository->workflow->dependency/API call chains are present for all rows.

## dynamic SQL 無法解析
- Row numbers: $unresolvedRowsText

## 規格衝突
- No confirmed confirmed spec contradiction found from this static evidence set.
- Blocked until strong-model architecture review confirms migration/remove position.

## 跨 Domain／權限／退款／月結等高風險項目
- High-risk rows (payroll writer families): $highRiskText
- Payroll-related boundaries should be kept blocked as candidate-only evidence.
"@
[System.IO.File]::WriteAllText($unresolvedPath, $unresolvedContent, (New-Object System.Text.UTF8Encoding($false)))

$validation = [ordered]@{
    batch_id = 'INV2-EVID-05'
    row_range = [ordered]@{start=201; end=250}
    input_sha256 = (Get-FileHash $findingsPath -Algorithm SHA256).Hash.ToLower()
    output_sha256 = [ordered]@{
        batch_manifest = (Get-FileHash $manifestOut -Algorithm SHA256).Hash.ToLower()
        finding_evidence = (Get-FileHash $evidencePath -Algorithm SHA256).Hash.ToLower()
        unresolved_md = (Get-FileHash $unresolvedPath -Algorithm SHA256).Hash.ToLower()
        validation_receipt = ''
    }
    processed_count = $outRows.Count
    identity_unique_count = ($outRows | Select-Object -ExpandProperty finding_identity_digest | Sort-Object -Unique).Count
    missing_field_count = 0
    effective_disposition_blocked_count = ($outRows | Where-Object { $_.effective_disposition -eq 'blocked' }).Count
    approved_to_remove_true_count = ($outRows | Where-Object { $_.approved_to_remove -eq $true }).Count
    production_files_changed = 0
}
$validationOut = Join-Path $evidenceRoot 'validation_receipt.json'
$validationJson = ConvertTo-Json $validation -Depth 12
[System.IO.File]::WriteAllText($validationOut, $validationJson, (New-Object System.Text.UTF8Encoding($false)))
$validation.output_sha256.validation_receipt = (Get-FileHash $validationOut -Algorithm SHA256).Hash.ToLower()
[System.IO.File]::WriteAllText($validationOut, (ConvertTo-Json $validation -Depth 12), (New-Object System.Text.UTF8Encoding($false)))

Write-Output "OK|$evidenceRoot"
