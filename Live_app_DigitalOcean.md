# CityFlow — Live Deployment

The CityFlow Traffic Intelligence dashboard is deployed on DigitalOcean App Platform.

**Live app URL:**  
[https://midterm5381-ecv6k.ondigitalocean.app/](https://midterm5381-ecv6k.ondigitalocean.app/)

- **Dashboard (home):** [https://midterm5381-ecv6k.ondigitalocean.app/](https://midterm5381-ecv6k.ondigitalocean.app/)
- **API docs:** [https://midterm5381-ecv6k.ondigitalocean.app/docs](https://midterm5381-ecv6k.ondigitalocean.app/docs)

To use the dashboard, ensure the app has valid `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, and `OPENAI_API_KEY` configured in the DigitalOcean app environment, and that the Supabase database has been set up with `sql/schema.sql` and seeded (e.g. via `scripts/generate_data.py`).
