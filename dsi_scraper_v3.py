import os
import requests
import pandas as pd
import yaml
import time
import logging
import tldextract
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from rapidfuzz import fuzz
from dateutil import parser as date_parser
from tenacity import retry, stop_after_attempt, wait_exponential

# Setup Logging - No silent failures
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("dsi_v3_run.log"), logging.StreamHandler()]
)

class DSIScraperV3:
    def __init__(self):
        self.target_date = datetime.now()
        self.results = []
        self.rejected = []
        self.source_stats = {}
        
        # ICP Constants
        self.STRICT_ROLES = [
            'backend', 'frontend', 'fullstack', 'software engineer', 'mobile', 
            'devops', 'sre', 'qa automation', 'data engineer', 'ai engineer', 'ml engineer'
        ]
        
        self.HARD_REJECT_KEYWORDS = [
            'us only', 'usa only', 'canada only', 'uk only', 'europe only', 'eu only',
            'emea', 'apac', 'latam', 'visa sponsorship not available', 'work authorization required',
            'must reside in', 'must be located in', 'hybrid', 'onsite', 'office required'
        ]
        
        self.GLOBAL_SIGNALS = [
            'worldwide', 'work from anywhere', 'anywhere in the world', 'global remote',
            'open globally', 'location independent', 'fully distributed'
        ]

    def normalize_title(self, title):
        title = title.lower()
        removals = ['senior', 'sr', 'lead', 'principal', 'staff', 'junior', 'mid', 'remote', 'worldwide']
        for r in removals:
            title = title.replace(r, '').strip()
        return title

    def calculate_score(self, job):
        score = 0
        reasons = []

        # 1. Location & Global Remote (Max 50)
        loc_raw = str(job.get('location_raw', '')).lower()
        desc = str(job.get('description', '')).lower()
        
        is_global = any(sig in loc_raw or sig in desc for sig in self.GLOBAL_SIGNALS)
        if is_global:
            score += 45
            reasons.append("Strong Global Signal")
        
        # 2. Role Match (Max 15)
        norm_title = self.normalize_title(job['job_title'])
        if any(role in norm_title for role in self.STRICT_ROLES):
            score += 15
            reasons.append("Core Engineering Role")

        # 3. Freshness (Max 10)
        days_old = job.get('days_old', 99)
        if days_old <= 7:
            score += 10
        elif days_old <= 14:
            score += 5

        # 4. Source Trust (Max 10)
        score += job.get('source_trust_score', 0)

        return score, "; ".join(reasons)

    def is_hard_reject(self, job):
        text_to_scan = (str(job.get('job_title', '')) + " " + 
                        str(job.get('location_raw', '')) + " " + 
                        str(job.get('description', ''))).lower()
        
        # Check for location restrictions
        if any(reject in text_to_scan for reject in self.HARD_REJECT_KEYWORDS):
            return True, "Location/Visa Restriction"
        
        # Check for non-engineering roles
        reject_roles = ['manager', 'product', 'designer', 'recruiter', 'support', 'sales']
        if any(role in text_to_scan for role in reject_roles) and "engineer" not in text_to_scan:
            return True, "Non-Engineering Role"
            
        return False, ""

    def process_job(self, job):
        # Apply Hard Rejects
        rejected, reason = self.is_hard_reject(job)
        if rejected:
            job['reject_reason'] = reason
            self.rejected.append(job)
            return

        # Score the job
        score, reasons = self.calculate_score(job)
        job['dsi_icp_score'] = score
        job['score_reasons'] = reasons
        
        # Determine output bucket
        if score >= 80:
            job['bucket'] = 'strict'
        elif score >= 50:
            job['bucket'] = 'secondary'
        else:
            job['bucket'] = 'needs_verification'
            
        self.results.append(job)

    def run(self):
        logging.info("Starting DSI V3 Scrape...")
        # In a real scenario, this would loop through sources.yml
        # Mocking one successful pull for demonstration
        mock_job = {
            'collected_date': datetime.now().strftime('%Y-%m-%d'),
            'company_name': 'TechFlow SaaS',
            'company_domain': 'techflow.io',
            'job_title': 'Senior Backend Engineer (Go)',
            'location_raw': 'Remote Worldwide',
            'job_url': 'https://techflow.io/jobs/123',
            'description': 'We are a fully distributed team. Hire from anywhere in the world.',
            'days_old': 2,
            'source_trust_score': 10,
            'company_headcount_bucket': '51-100'
        }
        self.process_job(mock_job)
        
        self.export_data()

    def export_data(self):
        df = pd.DataFrame(self.results)
        if not df.empty:
            df[df['bucket'] == 'strict'].to_csv(f"dsi_v3_strict_icp_{datetime.now().strftime('%Y%m%d')}.csv", index=False)
            df[df['bucket'] == 'secondary'].to_csv(f"dsi_v3_secondary_{datetime.now().strftime('%Y%m%d')}.csv", index=False)
        
        pd.DataFrame(self.rejected).to_csv(f"dsi_v3_rejected_{datetime.now().strftime('%Y%m%d')}.csv", index=False)
        logging.info(f"Run complete. Strict: {len(df[df['bucket'] == 'strict'] if not df.empty else [])}")

if __name__ == "__main__":
    scraper = DSIScraperV3()
    scraper.run()
