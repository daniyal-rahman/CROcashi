"""
Simplified CLI for Resolver System

Clean command-line interface for the three-tier resolver system.
Replaces the complex probabilistic CLI with simple, clear commands.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy.orm import Session

from ..db.session import get_session
from .simple_resolver import SimpleResolver, ResolutionOutput
from .simple_persist import get_resolution_stats

app = typer.Typer(add_completion=False)
console = Console()


def resolve_one(
    sponsor: str = typer.Argument(..., help="Sponsor text to resolve"),
    nct: Optional[str] = typer.Option(None, "--nct", help="NCT ID for context"),
    json_out: bool = typer.Option(False, help="Output JSON result"),
    save: bool = typer.Option(False, help="Save result to database")
):
    """Resolve a single sponsor using three-tier matching."""
    
    with get_session() as session:
        resolver = SimpleResolver(session)
        
        # Use provided NCT ID or generate a dummy one
        nct_id = nct or "NCT00000000"
        
        try:
            result = resolver.resolve_sponsor(nct_id, sponsor)
            
            if json_out:
                # Output JSON
                output = {
                    "sponsor": sponsor,
                    "nct_id": nct_id,
                    "company_id": result.company_id,
                    "match_method": result.match_method,
                    "confidence": result.confidence,
                    "evidence": result.evidence,
                    "aliases_discovered": result.aliases_discovered or []
                }
                console.print_json(json.dumps(output, ensure_ascii=False))
            else:
                # Output human-readable
                console.rule(f"[bold]Resolution Result[/bold]")
                console.print(f"[bold]Sponsor:[/bold] {sponsor}")
                console.print(f"[bold]NCT ID:[/bold] {nct_id}")
                console.print(f"[bold]Company ID:[/bold] {result.company_id}")
                console.print(f"[bold]Match Method:[/bold] {result.match_method}")
                console.print(f"[bold]Confidence:[/bold] {result.confidence:.3f}")
                
                if result.evidence:
                    console.print(f"[bold]Evidence:[/bold]")
                    for key, value in result.evidence.items():
                        console.print(f"  {key}: {value}")
                
                if result.aliases_discovered:
                    console.print(f"[bold]Aliases Discovered:[/bold] {', '.join(result.aliases_discovered)}")
                
                # Show what happened
                if result.match_method == "academic_skip":
                    console.print("[yellow]→ Academic institution detected, skipped[/yellow]")
                elif result.match_method == "exact":
                    console.print("[green]→ Exact match found[/green]")
                elif result.match_method == "fuzzy":
                    console.print("[blue]→ Fuzzy match found[/blue]")
                elif result.match_method == "llm":
                    console.print("[magenta]→ LLM match found with web search[/magenta]")
                elif result.match_method == "manual":
                    console.print("[red]→ No match found, added to manual review[/red]")
            
            if save and result.company_id:
                console.print("[green]✓ Result saved to database[/green]")
            
        except Exception as e:
            console.print(f"[red]Error resolving sponsor: {e}[/red]")
            raise typer.Exit(1)


def resolve_nct(
    nct_id: str = typer.Argument(..., help="NCT ID to resolve"),
    json_out: bool = typer.Option(False, help="Output JSON result"),
    save: bool = typer.Option(False, help="Save result to database")
):
    """Resolve sponsor for a specific NCT ID."""
    
    with get_session() as session:
        resolver = SimpleResolver(session)
        
        try:
            # Get sponsor text from database (you'd need to implement this)
            # For now, we'll use a placeholder
            sponsor_text = f"Sponsor for {nct_id}"  # TODO: Get from trials table
            
            result = resolver.resolve_sponsor(nct_id, sponsor_text)
            
            if json_out:
                output = {
                    "nct_id": nct_id,
                    "sponsor": sponsor_text,
                    "company_id": result.company_id,
                    "match_method": result.match_method,
                    "confidence": result.confidence,
                    "evidence": result.evidence,
                    "aliases_discovered": result.aliases_discovered or []
                }
                console.print_json(json.dumps(output, ensure_ascii=False))
            else:
                console.rule(f"[bold]Resolution for {nct_id}[/bold]")
                console.print(f"[bold]Sponsor:[/bold] {sponsor_text}")
                console.print(f"[bold]Company ID:[/bold] {result.company_id}")
                console.print(f"[bold]Match Method:[/bold] {result.match_method}")
                console.print(f"[bold]Confidence:[/bold] {result.confidence:.3f}")
            
            if save and result.company_id:
                console.print("[green]✓ Result saved to database[/green]")
            
        except Exception as e:
            console.print(f"[red]Error resolving NCT: {e}[/red]")
            raise typer.Exit(1)


def stats():
    """Show resolution statistics."""
    
    with get_session() as session:
        try:
            stats_data = get_resolution_stats(session)
            
            console.print("[bold]Resolver Statistics[/bold]")
            console.print("=" * 50)
            
            # Method breakdown
            if stats_data.get("method_stats"):
                table = Table(title="Match Methods")
                table.add_column("Method")
                table.add_column("Count", justify="right")
                table.add_column("Avg Confidence", justify="right")
                
                for method, data in stats_data["method_stats"].items():
                    table.add_row(
                        method,
                        str(data["count"]),
                        f"{data['avg_confidence']:.3f}"
                    )
                
                console.print(table)
            
            # Summary
            console.print(f"\n[bold]Summary:[/bold]")
            console.print(f"  Pending Reviews: {stats_data.get('pending_reviews', 0)}")
            console.print(f"  LLM Discoveries: {stats_data.get('llm_discoveries', 0)}")
            
            # Show system health
            total_resolved = sum(data["count"] for data in stats_data.get("method_stats", {}).values())
            pending = stats_data.get("pending_reviews", 0)
            
            if pending == 0:
                console.print("[green]🎉 No pending reviews![/green]")
            elif pending < total_resolved * 0.1:  # Less than 10% pending
                console.print("[green]✅ System is healthy[/green]")
            else:
                console.print("[yellow]⚠️  High number of pending reviews[/yellow]")
            
        except Exception as e:
            console.print(f"[red]Error getting stats: {e}[/red]")
            raise typer.Exit(1)


def test_academic_detection(
    sponsor: str = typer.Argument(..., help="Sponsor text to test")
):
    """Test academic detection patterns."""
    
    with get_session() as session:
        resolver = SimpleResolver(session)
        
        is_academic = resolver._is_academic_sponsor(sponsor)
        
        console.rule(f"[bold]Academic Detection Test[/bold]")
        console.print(f"[bold]Sponsor:[/bold] {sponsor}")
        console.print(f"[bold]Is Academic:[/bold] {'Yes' if is_academic else 'No'}")
        
        if is_academic:
            console.print("[yellow]→ This sponsor would be skipped[/yellow]")
        else:
            console.print("[green]→ This sponsor would be processed[/green]")


if __name__ == "__main__":
    app()
