"""
arXiv paper fetcher module.
"""
import arxiv
from datetime import datetime, timedelta
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)


class ArxivFetcher:
    """arXiv paper fetcher."""

    def __init__(self, categories: List[str], max_results: int = 10):
        """
        Initialize arXiv fetcher.

        Args:
            categories: Category list, e.g. ['cs.AI', 'cs.CL']
            max_results: Max results per category
        """
        self.categories = categories
        self.max_results = max_results

    def fetch_daily_papers(self) -> List[Dict]:
        """
        Fetch daily latest papers.

        Returns:
            List of papers with title, authors, abstract, links, etc.
        """
        papers = []
        yesterday = datetime.now() - timedelta(days=1)

        for category in self.categories:
            try:
                logger.info(f"Fetching {category} papers...")

                search = arxiv.Search(
                    query=f"cat:{category}",
                    max_results=self.max_results,
                    sort_by=arxiv.SortCriterion.SubmittedDate,
                    sort_order=arxiv.SortOrder.Descending
                )

                for result in search.results():
                    if result.published.date() >= yesterday.date():
                        paper = {
                            'title': result.title,
                            'authors': [author.name for author in result.authors],
                            'abstract': result.summary,
                            'pdf_url': result.pdf_url,
                            'arxiv_url': result.entry_id,
                            'published': result.published.strftime('%Y-%m-%d'),
                            'category': category,
                            'source': 'arxiv'
                        }
                        papers.append(paper)

            except Exception as e:
                logger.error(f"Failed to fetch {category}: {str(e)}")

        logger.info(f"Fetched {len(papers)} papers from arXiv")
        return papers

    def search_papers(self, query: str, max_results: int = 5) -> List[Dict]:
        """
        Search papers by topic.

        Args:
            query: Search keywords
            max_results: Max results

        Returns:
            List of papers
        """
        papers = []
        try:
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending
            )
            for result in search.results():
                paper = {
                    'title': result.title,
                    'authors': [author.name for author in result.authors],
                    'abstract': result.summary,
                    'pdf_url': result.pdf_url,
                    'arxiv_url': result.entry_id,
                    'published': result.published.strftime('%Y-%m-%d'),
                    'source': 'arxiv'
                }
                papers.append(paper)
        except Exception as e:
            logger.error(f"Search failed: {str(e)}")
        return papers
