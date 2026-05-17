/* ============================================================
   Mock data for the Cpnt SQL Console
   Scenario: SELECT Cpnt setting for 'PCM_QUERY_V2' across fabs
   ============================================================ */

window.FABS = ['F12A','F12B','F14A','F14B','F15A','F15B','F16','F18A','F18B','F21','F22','F23','APOD','SOIC'];

window.SCENARIOS = [
  { id: '__free',  label: '— Free SQL —',                       params: [] },
  { id: 'cpnt_by_name', label: 'CPNT · 依名稱查積木設定',         params: [{k:'cpnt_name', placeholder:'PCM_QUERY_V2'}] },
  { id: 'sop_by_id',    label: 'SOP · 依 SOP_ID 查 SOP 步驟',     params: [{k:'sop_id', placeholder:'SOP-PCM-0034'}] },
  { id: 'failed_24h',   label: 'CPNT · 24h 內失敗率 > 30%',       params: [{k:'threshold', placeholder:'0.30'}] },
  { id: 'cpnt_by_owner',label: 'CPNT · 依 OWNER 查 Cpnt 清單',    params: [{k:'owner', placeholder:'rd_pcm_team'}] },
];

window.SAMPLE_SQL = `-- Cpnt config lookup across fabs
SELECT  c.cpnt_id,
        c.cpnt_name,
        c.endpoint_url,
        c.method,
        c.timeout_ms,
        c.retry_count,
        c.auth_mode,
        c.enabled,
        c.owner,
        c.updated_by,
        TO_CHAR(c.updated_at,'YYYY-MM-DD HH24:MI') AS updated_at
FROM    isop_cpnt c
WHERE   c.cpnt_name = :cpnt_name
  AND   ROWNUM <= 100`;

/* Results — each fab gets a row. Designed to show diffs in:
   endpoint_url (host segment), timeout_ms, retry_count, auth_mode, enabled, version
*/
window.RESULTS = [
  { fab:'F12A', status:'ok',  data:{ cpnt_id:'CPN-00871', cpnt_name:'PCM_QUERY_V2', endpoint_url:'http://isop-f12a.tsmc.intra/api/pcm/v2/query', method:'POST', timeout_ms:5000,  retry_count:3, auth_mode:'OAUTH2', enabled:'Y', owner:'rd_pcm_team', updated_by:'lin.eric',  updated_at:'2026-05-03 14:21' } },
  { fab:'F12B', status:'ok',  data:{ cpnt_id:'CPN-00871', cpnt_name:'PCM_QUERY_V2', endpoint_url:'http://isop-f12b.tsmc.intra/api/pcm/v2/query', method:'POST', timeout_ms:5000,  retry_count:3, auth_mode:'OAUTH2', enabled:'Y', owner:'rd_pcm_team', updated_by:'lin.eric',  updated_at:'2026-05-03 14:21' } },
  { fab:'F14A', status:'ok',  data:{ cpnt_id:'CPN-00871', cpnt_name:'PCM_QUERY_V2', endpoint_url:'http://isop-f14a.tsmc.intra/api/pcm/v2/query', method:'POST', timeout_ms:8000,  retry_count:3, auth_mode:'OAUTH2', enabled:'Y', owner:'rd_pcm_team', updated_by:'wang.k',    updated_at:'2026-04-28 09:02' } },
  { fab:'F14B', status:'ok',  data:{ cpnt_id:'CPN-00871', cpnt_name:'PCM_QUERY_V2', endpoint_url:'http://isop-f14b.tsmc.intra/api/pcm/v2/query', method:'POST', timeout_ms:8000,  retry_count:3, auth_mode:'OAUTH2', enabled:'Y', owner:'rd_pcm_team', updated_by:'wang.k',    updated_at:'2026-04-28 09:02' } },
  { fab:'F15A', status:'ok',  data:{ cpnt_id:'CPN-00871', cpnt_name:'PCM_QUERY_V2', endpoint_url:'http://isop-f15a.tsmc.intra/api/pcm/v2/query', method:'POST', timeout_ms:5000,  retry_count:3, auth_mode:'OAUTH2', enabled:'Y', owner:'rd_pcm_team', updated_by:'lin.eric',  updated_at:'2026-05-03 14:21' } },
  { fab:'F15B', status:'ok',  data:{ cpnt_id:'CPN-00871', cpnt_name:'PCM_QUERY_V2', endpoint_url:'http://isop-f15b.tsmc.intra/api/pcm/v2/query', method:'POST', timeout_ms:5000,  retry_count:3, auth_mode:'OAUTH2', enabled:'N', owner:'rd_pcm_team', updated_by:'chen.may',  updated_at:'2026-05-10 18:44' } },
  { fab:'F16',  status:'ok',  data:{ cpnt_id:'CPN-00871', cpnt_name:'PCM_QUERY_V2', endpoint_url:'http://isop-f16.tsmc.intra/api/pcm/v2/query',  method:'POST', timeout_ms:5000,  retry_count:5, auth_mode:'OAUTH2', enabled:'Y', owner:'rd_pcm_team', updated_by:'huang.s',   updated_at:'2026-05-12 11:30' } },
  { fab:'F18A', status:'ok',  data:{ cpnt_id:'CPN-00871', cpnt_name:'PCM_QUERY_V2', endpoint_url:'http://isop-f18a.tsmc.intra/api/pcm/v2/query', method:'POST', timeout_ms:5000,  retry_count:3, auth_mode:'OAUTH2', enabled:'Y', owner:'rd_pcm_team', updated_by:'lin.eric',  updated_at:'2026-05-03 14:21' } },
  { fab:'F18B', status:'ok',  data:{ cpnt_id:'CPN-00871', cpnt_name:'PCM_QUERY_V2', endpoint_url:'http://isop-f18b.tsmc.intra/api/pcm/v2/query', method:'POST', timeout_ms:5000,  retry_count:3, auth_mode:'OAUTH2', enabled:'Y', owner:'rd_pcm_team', updated_by:'lin.eric',  updated_at:'2026-05-03 14:21' } },
  { fab:'F21',  status:'err', error:'ORA-12170: TNS:Connect timeout occurred' },
  { fab:'F22',  status:'ok',  data:{ cpnt_id:'CPN-00871', cpnt_name:'PCM_QUERY_V2', endpoint_url:'http://isop-f22.tsmc.intra/api/pcm/v2/query',  method:'POST', timeout_ms:5000,  retry_count:3, auth_mode:'OAUTH2', enabled:'Y', owner:'rd_pcm_team', updated_by:'lin.eric',  updated_at:'2026-05-03 14:21' } },
  { fab:'F23',  status:'ok',  data:{ cpnt_id:'CPN-00872', cpnt_name:'PCM_QUERY_V2', endpoint_url:'http://isop-f23.tsmc.intra/api/pcm/v2/query',  method:'POST', timeout_ms:10000, retry_count:3, auth_mode:'BASIC',  enabled:'Y', owner:'rd_pcm_team', updated_by:'tsai.benny', updated_at:'2026-02-17 10:08' } },
  { fab:'APOD', status:'err', error:'ORA-00942: table or view does not exist (isop_cpnt)' },
  { fab:'SOIC', status:'ok',  data:{ cpnt_id:'CPN-00871', cpnt_name:'PCM_QUERY_V2', endpoint_url:'http://isop-soic.tsmc.intra/api/pcm/v2/query', method:'POST', timeout_ms:5000,  retry_count:3, auth_mode:'OAUTH2', enabled:'Y', owner:'rd_pcm_team', updated_by:'lin.eric',  updated_at:'2026-05-03 14:21' } },
];

window.COLUMNS = [
  { k:'cpnt_id',      label:'CPNT_ID' },
  { k:'cpnt_name',    label:'CPNT_NAME' },
  { k:'endpoint_url', label:'ENDPOINT_URL' },
  { k:'method',       label:'METHOD' },
  { k:'timeout_ms',   label:'TIMEOUT_MS' },
  { k:'retry_count',  label:'RETRY_COUNT' },
  { k:'auth_mode',    label:'AUTH_MODE' },
  { k:'enabled',      label:'ENABLED' },
  { k:'owner',        label:'OWNER' },
  { k:'updated_by',   label:'UPDATED_BY' },
  { k:'updated_at',   label:'UPDATED_AT' },
];
