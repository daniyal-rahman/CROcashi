#!/usr/bin/env python3
"""
Manual Review CLI for Resolver System

Simple command-line interface for reviewing unresolved sponsors.
Shows trials that need manual review and allows fuzzy search of companies.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import typer
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from ncfd.db.models import ManualReviewQueue, Company
from ncfd.mapping.simple_persist import get_pending_reviews, complete_review, skip_review

app = typer.Typer(add_completion=False)
console = Console()


def get_database_session():
    """Get database session."""
    database_url = os.environ.get('DATABASE_URL', 'postgresql://ncfd:ncfd@localhost:5433/ncfd')
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    return Session()


def search_companies(session, search_term: str, limit: int = 10):
    """Search companies using fuzzy matching."""
    try:
        result = session.execute(text("""
            SELECT 
                company_id,
                name,
                ticker,
                website_domain,
                similarity(name_norm, :search_term) as sim_score
            FROM companies
            WHERE name_norm % :search_term
            ORDER BY sim_score DESC
            LIMIT :limit
        """), {"search_term": search_term.lower(), "limit": limit})
        
        return result.fetchall()
    except Exception as e:
        console.print(f"[red]Error searching companies: {e}[/red]")
        return []


def display_companies(companies):
    """Display companies in a table."""
    if not companies:
        console.print("[yellow]No companies found[/yellow]")
        return
    
    table = Table(title="Matching Companies")
    table.add_column("ID", justify="right")
    table.add_column("Name")
    table.add_column("Ticker")
    table.add_column("Domain")
    table.add_column("Score", justify="right")
    
    for company in companies:
        table.add_row(
            str(company.company_id),
            company.name,
            company.ticker or "",
            company.website_domain or "",
            f"{company.sim_score:.3f}"
        )
    
    console.print(table)


def review_trial(session, review_item):
    """Review a single trial."""
    console.rule(f"[bold]Reviewing Trial {review_item.nct_id}[/bold]")
    console.print(f"[bold]Sponsor:[/bold] {review_item.sponsor_text}")
    console.print(f"[bold]NCT ID:[/bold] {review_item.nct_id}")
    console.print(f"[bold]Created:[/bold] {review_item.created_at}")
    
    while True:
        action = Prompt.ask(
            "\n[bold]Action[/bold]",
            choices=["search", "select", "skip", "quit"],
            default="search"
        )
        
        if action == "quit":
            return "quit"
        
        elif action == "skip":
            reason = Prompt.ask("Skip reason", default="No suitable match found")
            skip_review(session, review_item.id, reason)
            console.print(f"[yellow]Skipped trial {review_item.nct_id}[/yellow]")
            return "next"
        
        elif action == "search":
            search_term = Prompt.ask("Search companies")
            if search_term:
                companies = search_companies(session, search_term)
                display_companies(companies)
        
        elif action == "select":
            try:
                company_id = int(Prompt.ask("Enter company ID"))
                
                # Verify company exists
                company = session.query(Company).filter(
                    Company.company_id == company_id
                ).first()
                
                if company:
                    notes = Prompt.ask("Review notes", default="Manual review completed")
                    complete_review(session, review_item.id, company_id, notes)
                    console.print(f"[green]Assigned trial {review_item.nct_id} to company {company_id}[/green]")
                    return "next"
                else:
                    console.print(f"[red]Company {company_id} not found[/red]")
            except ValueError:
                console.print("[red]Invalid company ID[/red]")


@app.command()
def review(
    limit: int = typer.Option(10, help="Number of trials to review"),
    batch: bool = typer.Option(False, help="Batch mode (no interactive prompts)")
):
    """Review unresolved sponsors manually."""
    session = get_database_session()
    
    try:
        # Get pending reviews
        pending_reviews = get_pending_reviews(session, limit)
        
        if not pending_reviews:
            console.print("[green]No pending reviews! 🎉[/green]")
            return
        
        console.print(f"[bold]Found {len(pending_reviews)} pending reviews[/bold]")
        
        if batch:
            # Batch mode - just show the list
            table = Table(title="Pending Reviews")
            table.add_column("ID", justify="right")
            table.add_column("NCT ID")
            table.add_column("Sponsor")
            table.add_column("Created")
            
            for review_item in pending_reviews:
                table.add_row(
                    str(review_item.id),
                    review_item.nct_id,
                    review_item.sponsor_text[:50] + "..." if len(review_item.sponsor_text) > 50 else review_item.sponsor_text,
                    str(review_item.created_at.date())
                )
            
            console.print(table)
            return
        
        # Interactive mode
        for i, review_item in enumerate(pending_reviews, 1):
            console.print(f"\n[bold]Review {i}/{len(pending_reviews)}[/bold]")
            
            result = review_trial(session, review_item)
            
            if result == "quit":
                console.print("[yellow]Review session ended[/yellow]")
                break
            elif result == "next":
                continue
        
        console.print("[green]Review session completed![/green]")
        
    except Exception as e:
        console.print(f"[red]Error during review: {e}[/red]")
    finally:
        session.close()


@app.command()
def stats():
    """Show resolution statistics."""
    session = get_database_session()
    
    try:
        # Get stats from simple_persist
        from ncfd.mapping.simple_persist import get_resolution_stats
        stats = get_resolution_stats(session)
        
        console.print("[bold]Resolution Statistics[/bold]")
        console.print("=" * 50)
        
        # Method stats
        if stats.get("method_stats"):
            table = Table(title="Match Methods")
            table.add_column("Method")
            table.add_column("Count", justify="right")
            table.add_column("Avg Confidence", justify="right")
            
            for method, data in stats["method_stats"].items():
                table.add_row(
                    method,
                    str(data["count"]),
                    f"{data['avg_confidence']:.3f}"
                )
            
            console.print(table)
        
        # Summary stats
        console.print(f"\n[bold]Summary:[/bold]")
        console.print(f"  Pending Reviews: {stats.get('pending_reviews', 0)}")
        console.print(f"  LLM Discoveries: {stats.get('llm_discoveries', 0)}")
        
    except Exception as e:
        console.print(f"[red]Error getting stats: {e}[/red]")
    finally:
        session.close()


@app.command()
def learn():
    """Learn aliases from LLM discoveries."""
    session = get_database_session()
    
    try:
        from ncfd.mapping.simple_persist import learn_aliases_from_discoveries
        
        console.print("[bold]Learning aliases from LLM discoveries...[/bold]")
        
        aliases_learned = learn_aliases_from_discoveries(session, min_confidence=0.85)
        
        console.print(f"[green]Learned {aliases_learned} new aliases![/green]")
        
    except Exception as e:
        console.print(f"[red]Error learning aliases: {e}[/red]")
    finally:
        session.close()


if __name__ == "__main__":
    app()
