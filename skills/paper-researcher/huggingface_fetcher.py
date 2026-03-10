"""
HuggingFace paper fetcher module.
"""
import requests
from bs4 import BeautifulSoup
from typing import List, Dict
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class HuggingFaceFetcher:
    """HuggingFace daily paper fetcher."""

    def __init__(self, max_results: int = 10):
        """
        Initialize HuggingFace fetcher.

        Args:
            max_results: Max results to fetch
        """
        self.base_url = "https://huggingface.co/papers"
        self.max_results = max_results
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

    def fetch_daily_papers(self) -> List[Dict]:
        """
        Fetch HuggingFace daily papers.

        Returns:
            List of papers
        """
        papers = []
        try:
            logger.info("Fetching HuggingFace papers...")
            response = requests.get(self.base_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            paper_cards = soup.find_all('article', class_='overview-card-wrapper', limit=self.max_results)

            for card in paper_cards:
                try:
                    title_elem = card.find('h3')
                    title = title_elem.text.strip() if title_elem else "Unknown"
                    link_elem = card.find('a', href=True)
                    paper_link = f"https://huggingface.co{link_elem['href']}" if link_elem else ""
                    authors_elem = card.find('p', class_='text-sm')
                    authors = [authors_elem.text.strip()] if authors_elem else []
                    abstract_elem = card.find('p', class_='line-clamp-3')
                    abstract = abstract_elem.text.strip() if abstract_elem else ""
                    likes_elem = card.find('span', class_='text-sm')
                    likes = likes_elem.text.strip() if likes_elem else "0"

                    paper = {
                        'title': title,
                        'authors': authors,
                        'abstract': abstract,
                        'url': paper_link,
                        'likes': likes,
                        'published': datetime.now().strftime('%Y-%m-%d'),
                        'source': 'huggingface'
                    }
                    papers.append(paper)
                except Exception as e:
                    logger.warning(f"Parse failed for one card: {str(e)}")
                    continue

            logger.info(f"Fetched {len(papers)} papers from HuggingFace")
        except Exception as e:
            logger.error(f"Fetch failed: {str(e)}")
        return papers
