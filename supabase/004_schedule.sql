\set VERBOSITY terse
\getenv tankerkoenig_api_key TANKERKOENIG_API_KEY

select vault.update_secret(id, :'tankerkoenig_api_key')
from vault.secrets where name = 'tankerkoenig_api_key';

select vault.create_secret(:'tankerkoenig_api_key', 'tankerkoenig_api_key')
where not exists (select 1 from vault.secrets where name = 'tankerkoenig_api_key');

\unset tankerkoenig_api_key
\set VERBOSITY default

select cron.unschedule(jobname) from cron.job where jobname in ('pumpwatch-collect', 'pumpwatch-prune');

select cron.schedule('pumpwatch-collect', '3-59/5 * * * *', $$select public.collect_prices()$$);
select cron.schedule('pumpwatch-prune',  '7-59/10 * * * *', $$select public.prune_http_responses()$$);
