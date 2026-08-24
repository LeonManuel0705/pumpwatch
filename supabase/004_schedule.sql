select vault.create_secret('REPLACE_WITH_YOUR_API_KEY', 'tankerkoenig_api_key');

select cron.schedule('pumpwatch-collect', '* * * * *', $$select public.collect_prices()$$);
select cron.schedule('pumpwatch-prune',  '*/10 * * * *', $$select public.prune_http_responses()$$);
