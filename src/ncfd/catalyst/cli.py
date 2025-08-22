"""Terminal-based CLI for Phase 10 Catalyst System with LLM Integration."""

import argparse
import sys
import asyncio
import json
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt, Confirm
from rich import box

from .models import RankedTrial, StudyCardRanking, LLMResolutionScore
from .rank import sort_ranked_trials, get_ranking_summary, filter_trials_by_criteria
from .automated_evaluation import (
    AutomatedEvaluationSystem, AutomatedEvaluationRequest,
    evaluate_study_cards_automated_sync
)
from .llm_resolution import LLMResolutionService, resolve_study_card_rankings_sync
from .comprehensive_service import ComprehensiveStudyCardService


class CatalystCLI:
    """Command-line interface for the catalyst system."""
    
    def __init__(self):
        self.console = Console()
        self.trials: List[RankedTrial] = []
        self.eval_system = AutomatedEvaluationSystem()
        self.llm_service = LLMResolutionService()
        self.comprehensive_service = ComprehensiveStudyCardService()
        
    def display_banner(self):
        """Display the catalyst system banner."""
        banner = Text("🚀 Phase 10 Catalyst System", style="bold blue")
        subtitle = Text("AI-powered precision failure detection with GPT-5 resolution", style="italic")
        features = Text("✨ Automated evaluation • LLM tie-breaking • Comprehensive analysis", style="dim")
        
        panel = Panel(
            f"{banner}\n{subtitle}\n{features}",
            box=box.ROUNDED,
            border_style="blue"
        )
        self.console.print(panel)
    
    def display_trials_table(self, trials: List[RankedTrial], title: str = "Ranked Trials"):
        """Display trials in a formatted table."""
        if not trials:
            self.console.print("No trials found.", style="yellow")
            return
        
        table = Table(title=title, box=box.ROUNDED)
        table.add_column("Rank", style="cyan", no_wrap=True)
        table.add_column("Ticker", style="green", no_wrap=True)
        table.add_column("Phase", style="blue", no_wrap=True)
        table.add_column("Study Score", style="yellow", no_wrap=True)
        table.add_column("LLM Score", style="magenta", no_wrap=True)
        table.add_column("P_fail", style="red", no_wrap=True)
        table.add_column("Window", style="white", no_wrap=True)
        table.add_column("Gates", style="white", no_wrap=True)
        
        for i, trial in enumerate(trials, 1):
            window_str = f"{trial.window_start} → {trial.window_end}" if trial.window_start and trial.window_end else "N/A"
            gates_str = ", ".join(trial.gates) if trial.gates else "None"
            
            table.add_row(
                str(i),
                trial.ticker,
                trial.phase,
                f"{trial.study_card_score:.1f}",
                f"{trial.llm_resolution_score:.0f}" if trial.llm_resolution_score > 0 else "N/A",
                f"{trial.p_fail:.2f}",
                window_str,
                gates_str
            )
        
        self.console.print(table)
    
    def display_ranking_summary(self, trials: List[RankedTrial]):
        """Display ranking summary statistics."""
        if not trials:
            return
        
        summary = get_ranking_summary(trials)
        
        summary_panel = Panel(
            f"📊 Ranking Summary\n\n"
            f"Total Trials: {summary['total_trials']}\n"
            f"High Priority (7-10): {summary['high_priority_count']}\n"
            f"Medium Priority (4-6): {summary['medium_priority_count']}\n"
            f"Low Priority (1-3): {summary['low_priority_count']}\n"
            f"Average Confidence: {summary['avg_confidence']:.2f}\n"
            f"Average Proximity: {summary['avg_proximity']:.0f} days",
            title="Statistics",
            border_style="green"
        )
        
        self.console.print(summary_panel)
    
    def display_trial_details(self, trial: RankedTrial):
        """Display detailed information about a specific trial."""
        details = f"""
🔍 Trial Details: {trial.ticker}

Basic Information:
  • Trial ID: {trial.trial_id}
  • NCT ID: {trial.nct_id}
  • Phase: {trial.phase}

Scores:
  • Study Card Score: {trial.study_card_score:.1f}/10
  • LLM Resolution Score: {trial.llm_resolution_score:.0f}/100
  • P_fail: {trial.p_fail:.3f}
  • Certainty: {trial.certainty:.2f}

Catalyst Window:
  • Start: {trial.window_start or 'N/A'}
  • End: {trial.window_end or 'N/A'}
  • Proximity: {trial.proximity_score} days

Gates: {', '.join(trial.gates) if trial.gates else 'None'}
        """
        
        panel = Panel(details, title=f"Trial: {trial.ticker}", border_style="blue")
        self.console.print(panel)
    
    def create_mock_study_card(self, study_id: int, trial_id: int) -> Dict[str, Any]:
        """Create a mock study card for evaluation."""
        return {
            'study_id': study_id,
            'trial_id': trial_id,
            'extracted_jsonb': {
                'trial_id': f'TRIAL_{trial_id:03d}',
                'study_title': f'Phase III Study of Drug {study_id} in Advanced Disease',
                'primary_endpoint': f'Overall survival in patients with advanced disease {study_id}',
                'secondary_endpoints': [
                    'Progression-free survival',
                    'Overall response rate',
                    'Safety and tolerability'
                ],
                'study_design': 'Randomized, double-blind, placebo-controlled',
                'sample_size': 500 + (study_id * 50),
                'statistical_power': 0.9,
                'primary_population': 'ITT',
                'protocol_changes': [
                    'Sample size increased from 400 to 500',
                    'Primary endpoint modified for clarity'
                ],
                'primary_results': {
                    'hazard_ratio': 0.75 + (study_id * 0.05),
                    'confidence_interval': [0.65, 0.85],
                    'p_value': 0.001 + (study_id * 0.0001),
                    'statistical_significance': True
                },
                'safety_summary': {
                    'grade_3_4_ae_rate': 0.15 + (study_id * 0.02),
                    'treatment_discontinuation': 0.08 + (study_id * 0.01)
                }
            },
            'quality_score': 0.7 + (study_id * 0.05),
            'quality_confidence': 0.8 + (study_id * 0.02)
        }
    
    def run_automated_evaluation(self):
        """Run automated evaluation on study cards."""
        self.console.print("\n🤖 Automated Study Card Evaluation", style="bold")
        
        # Get user input for evaluation settings
        num_cards = Prompt.ask("Number of study cards to evaluate", default="5")
        try:
            num_cards = int(num_cards)
        except ValueError:
            self.console.print("Invalid number. Using default of 5.", style="yellow")
            num_cards = 5
        
        use_llm = Confirm.ask("Use LLM resolution for tie-breaking?", default=True)
        
        # Create mock study cards
        study_cards = [self.create_mock_study_card(i, i) for i in range(1, num_cards + 1)]
        
        # Create evaluation request
        request = AutomatedEvaluationRequest(
            study_cards=study_cards,
            use_llm_resolution=use_llm,
            resolution_context="CLI automated evaluation",
            save_to_database=False
        )
        
        # Run evaluation with progress spinner
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            task = progress.add_task("Evaluating study cards...", total=None)
            
            try:
                # Run the evaluation
                result = evaluate_study_cards_automated_sync(request)
                progress.update(task, description="✅ Evaluation complete!")
                
                # Display results
                self.display_evaluation_results(result)
                
            except Exception as e:
                progress.update(task, description=f"❌ Evaluation failed: {e}")
                self.console.print(f"Error during evaluation: {e}", style="red")
    
    def display_evaluation_results(self, result):
        """Display automated evaluation results."""
        self.console.print(f"\n📊 Evaluation Results", style="bold green")
        
        # Summary table
        summary_table = Table(title="Evaluation Summary", box=box.ROUNDED)
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="yellow")
        
        summary_table.add_row("Total Cards Evaluated", str(len(result.evaluated_cards)))
        summary_table.add_row("Average Confidence", f"{result.average_confidence:.2f}")
        summary_table.add_row("Processing Time", f"{result.total_processing_time:.2f}s")
        summary_table.add_row("High-Risk Studies", str(len(result.high_risk_studies)))
        
        self.console.print(summary_table)
        
        # Results table
        results_table = Table(title="Study Card Rankings", box=box.ROUNDED)
        results_table.add_column("Rank", style="cyan")
        results_table.add_column("Study ID", style="green")
        results_table.add_column("Base Score", style="yellow")
        results_table.add_column("LLM Score", style="magenta")
        results_table.add_column("Confidence", style="blue")
        results_table.add_column("Risk", style="red")
        
        for card in result.evaluated_cards:
            risk_level = "🔴 High" if card in result.high_risk_studies else "🟢 Low"
            results_table.add_row(
                str(card.final_ranking_position),
                str(card.study_id),
                f"{card.base_quality_rank}/10",
                f"{card.llm_enhanced_score or 'N/A'}",
                f"{card.base_confidence:.2f}",
                risk_level
            )
        
        self.console.print(results_table)
        
        # Distribution
        if result.ranking_distribution:
            dist_table = Table(title="Quality Distribution", box=box.ROUNDED)
            dist_table.add_column("Category", style="cyan")
            dist_table.add_column("Count", style="yellow")
            dist_table.add_column("Percentage", style="green")
            
            total = len(result.evaluated_cards)
            for category, count in result.ranking_distribution.items():
                percentage = (count / total) * 100 if total > 0 else 0
                dist_table.add_row(
                    category.replace('_', ' ').title(),
                    str(count),
                    f"{percentage:.1f}%"
                )
            
            self.console.print(dist_table)
        
        # LLM Resolution Summary
        if result.llm_resolution_summary:
            llm_panel = Panel(
                result.llm_resolution_summary,
                title="LLM Resolution Summary",
                border_style="magenta"
            )
            self.console.print(llm_panel)
    
    def run_comprehensive_analysis(self):
        """Run comprehensive study card analysis."""
        self.console.print("\n🔬 Comprehensive Study Card Analysis", style="bold")
        
        # Get study card ID
        study_id = Prompt.ask("Study ID to analyze", default="1")
        trial_id = Prompt.ask("Trial ID to analyze", default="1")
        
        try:
            study_id = int(study_id)
            trial_id = int(trial_id)
        except ValueError:
            self.console.print("Invalid ID. Using defaults.", style="yellow")
            study_id, trial_id = 1, 1
        
        # Create mock study card
        mock_card = self.create_mock_study_card(study_id, trial_id)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            task = progress.add_task("Running comprehensive analysis...", total=None)
            
            try:
                # Run comprehensive analysis
                result = self.comprehensive_service.analyze_study_card_comprehensive(
                    study_id, trial_id, mock_card['extracted_jsonb']
                )
                progress.update(task, description="✅ Analysis complete!")
                
                # Display results
                self.display_comprehensive_results(result, study_id, trial_id)
                
            except Exception as e:
                progress.update(task, description=f"❌ Analysis failed: {e}")
                self.console.print(f"Error during analysis: {e}", style="red")
    
    def display_comprehensive_results(self, result, study_id: int, trial_id: int):
        """Display comprehensive analysis results."""
        self.console.print(f"\n🔬 Comprehensive Analysis: Study {study_id}, Trial {trial_id}", style="bold blue")
        
        # Basic evaluation
        eval_table = Table(title="Quality Analysis", box=box.ROUNDED)
        eval_table.add_column("Metric", style="cyan")
        eval_table.add_column("Value", style="yellow")
        
        eval_table.add_row("Quality Score", f"{result.quality_score:.2f}")
        eval_table.add_row("Quality Rank", f"{result.quality_rank}/10")
        eval_table.add_row("Quality Confidence", f"{result.quality_confidence:.2f}")
        eval_table.add_row("Overall Quality", result.overall_quality)
        eval_table.add_row("Evidence Strength", result.evidence_strength)
        eval_table.add_row("Data Completeness", f"{result.data_completeness:.2f}")
        
        self.console.print(eval_table)
        
        # Enhanced extraction summary
        enhanced_panel = Panel(
            f"Tone Analysis: {result.tone_analysis.overall_tone.value.title()}\n"
            f"Conflicts Count: {len(result.conflicts_funding.conflicts_of_interest)}\n"
            f"Funding Sources: {len(result.conflicts_funding.funding_sources)}\n"
            f"Journal Type: {result.publication_details.journal_type.value.title()}\n"
            f"Data Tables: {len(result.data_location.tables)}\n"
            f"Data Figures: {len(result.data_location.figures)}",
            title="Enhanced Analysis",
            border_style="green"
        )
        self.console.print(enhanced_panel)
        
        # Issues summary
        issues_panel = Panel(
            f"Total Issues: {result.total_issues}\n"
            f"Critical Issues: {result.critical_issues}\n"
            f"Major Issues: {result.major_issues}\n"
            f"Limitations: {len(result.reviewer_notes.limitations)}\n"
            f"Oddities: {len(result.reviewer_notes.oddities)}\n"
            f"Overall Confidence: {result.confidence:.2f}",
            title="Issues & Quality Assessment",
            border_style="yellow"
        )
        self.console.print(issues_panel)
    
    def run_llm_resolution_demo(self):
        """Demonstrate LLM resolution capabilities."""
        self.console.print("\n🧠 LLM Resolution Demo", style="bold")
        
        # Create multiple study cards with same base score
        study_cards = [self.create_mock_study_card(i, i) for i in range(1, 4)]
        
        # Set them all to the same base score for demonstration
        for card in study_cards:
            card['base_score_1_10'] = 6  # Medium score
        
        self.console.print("Created 3 study cards with identical base scores (6/10)")
        self.console.print("Running LLM resolution to break ties...")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            task = progress.add_task("Resolving with GPT-5...", total=None)
            
            try:
                # Prepare cards for resolution
                prepared_cards = self.llm_service.prepare_study_cards_for_resolution(study_cards)
                
                # Run LLM resolution (using fallback since we're not making real API calls)
                fallback_results = self.llm_service._fallback_resolution(prepared_cards)
                
                progress.update(task, description="✅ Resolution complete!")
                
                # Display results
                self.display_llm_resolution_results(fallback_results)
                
            except Exception as e:
                progress.update(task, description=f"❌ Resolution failed: {e}")
                self.console.print(f"Error during LLM resolution: {e}", style="red")
    
    def display_llm_resolution_results(self, results):
        """Display LLM resolution results."""
        self.console.print("\n🧠 LLM Resolution Results", style="bold magenta")
        
        results_table = Table(title="Enhanced 1-100 Scoring", box=box.ROUNDED)
        results_table.add_column("Study ID", style="cyan")
        results_table.add_column("Base Score", style="yellow")
        results_table.add_column("Enhanced Score", style="magenta")
        results_table.add_column("Confidence", style="blue")
        results_table.add_column("Reasoning", style="white")
        
        for result in sorted(results, key=lambda x: x.enhanced_score_1_100, reverse=True):
            results_table.add_row(
                str(result.study_id),
                f"{result.base_score_1_10}/10",
                f"{result.enhanced_score_1_100}/100",
                f"{result.confidence:.2f}",
                result.resolution_reasoning[:50] + "..." if len(result.resolution_reasoning) > 50 else result.resolution_reasoning
            )
        
        self.console.print(results_table)
        
        # Summary
        avg_enhanced = sum(r.enhanced_score_1_100 for r in results) / len(results)
        avg_confidence = sum(r.confidence for r in results) / len(results)
        
        summary_panel = Panel(
            f"Average Enhanced Score: {avg_enhanced:.1f}/100\n"
            f"Average Confidence: {avg_confidence:.2f}\n"
            f"Score Range: {min(r.enhanced_score_1_100 for r in results)}-{max(r.enhanced_score_1_100 for r in results)}",
            title="Resolution Summary",
            border_style="magenta"
        )
        self.console.print(summary_panel)
    
    def load_mock_data(self):
        """Load mock data for demonstration."""
        self.trials = [
            RankedTrial(
                trial_id=1,
                nct_id='NCT001',
                ticker='ABCD',
                phase='III',
                study_card_score=8.5,
                llm_resolution_score=85,
                certainty=0.8,
                p_fail=0.9,
                gates=['G1', 'G3']
            ),
            RankedTrial(
                trial_id=2,
                nct_id='NCT002',
                ticker='EFGH',
                phase='II',
                study_card_score=6.0,
                llm_resolution_score=65,
                certainty=0.6,
                p_fail=0.7,
                gates=['G2']
            ),
            RankedTrial(
                trial_id=3,
                nct_id='NCT003',
                ticker='IJKL',
                phase='III',
                study_card_score=9.0,
                llm_resolution_score=92,
                certainty=0.9,
                p_fail=0.95,
                gates=['G1', 'G2', 'G4']
            ),
            RankedTrial(
                trial_id=4,
                nct_id='NCT004',
                ticker='MNOP',
                phase='II/III',
                study_card_score=4.5,
                llm_resolution_score=45,
                certainty=0.5,
                p_fail=0.6,
                gates=[]
            )
        ]
        
        # Sort trials
        today = date.today()
        self.trials = sort_ranked_trials(self.trials, today)
    
    def run_interactive_mode(self):
        """Run the CLI in interactive mode."""
        self.display_banner()
        self.load_mock_data()
        
        while True:
            self.console.print("\n" + "="*80)
            self.console.print("📋 Basic Commands:", style="bold")
            self.console.print("  list       - Show ranked trials")
            self.console.print("  summary    - Show ranking summary")
            self.console.print("  details    - Show trial details")
            self.console.print("  filter     - Filter trials by criteria")
            self.console.print("\n🤖 AI-Powered Commands:", style="bold")
            self.console.print("  evaluate   - Run automated study card evaluation")
            self.console.print("  analyze    - Run comprehensive study card analysis")
            self.console.print("  resolve    - Demonstrate LLM resolution")
            self.console.print("\n🚪 Exit:", style="bold")
            self.console.print("  quit       - Exit the application")
            self.console.print("="*80)
            
            try:
                command = input("\nEnter command: ").strip().lower()
                
                if command == 'quit':
                    self.console.print("Goodbye! 👋", style="green")
                    break
                elif command == 'list':
                    self.display_trials_table(self.trials)
                elif command == 'summary':
                    self.display_ranking_summary(self.trials)
                elif command == 'details':
                    try:
                        trial_num = int(input("Enter trial number (1-{}): ".format(len(self.trials))))
                        if 1 <= trial_num <= len(self.trials):
                            self.display_trial_details(self.trials[trial_num - 1])
                        else:
                            self.console.print("Invalid trial number.", style="red")
                    except ValueError:
                        self.console.print("Please enter a valid number.", style="red")
                elif command == 'filter':
                    self.run_filter_mode()
                elif command == 'evaluate':
                    self.run_automated_evaluation()
                elif command == 'analyze':
                    self.run_comprehensive_analysis()
                elif command == 'resolve':
                    self.run_llm_resolution_demo()
                else:
                    self.console.print("Unknown command. Available commands: list, summary, details, filter, evaluate, analyze, resolve, quit", style="red")
                    
            except KeyboardInterrupt:
                self.console.print("\nGoodbye! 👋", style="green")
                break
            except Exception as e:
                self.console.print(f"Error: {e}", style="red")
    
    def run_filter_mode(self):
        """Run filtering mode."""
        self.console.print("\n🔍 Filter Trials", style="bold")
        self.console.print("Enter filter criteria (press Enter to skip):")
        
        try:
            min_score_input = input("Minimum study card score (1-10): ").strip()
            min_score = float(min_score_input) if min_score_input else None
            
            max_score_input = input("Maximum study card score (1-10): ").strip()
            max_score = float(max_score_input) if max_score_input else None
            
            min_confidence_input = input("Minimum confidence (0.0-1.0): ").strip()
            min_confidence = float(min_confidence_input) if min_confidence_input else None
            
            phases_input = input("Phases (comma-separated, e.g., II,III): ").strip()
            phases = [p.strip() for p in phases_input.split(',')] if phases_input else None
            
            # Apply filters
            filtered_trials = filter_trials_by_criteria(
                self.trials,
                min_score=min_score,
                max_score=max_score,
                min_confidence=min_confidence,
                phases=phases
            )
            
            self.console.print(f"\n✅ Filtered to {len(filtered_trials)} trials")
            self.display_trials_table(filtered_trials, "Filtered Trials")
            
        except ValueError as e:
            self.console.print(f"Invalid input: {e}", style="red")
    
    def run_list_mode(self, args):
        """Run in list mode (non-interactive)."""
        self.load_mock_data()
        
        if args.filter:
            # Apply filters
            filtered_trials = filter_trials_by_criteria(
                self.trials,
                min_score=args.min_score,
                max_score=args.max_score,
                phases=args.phases.split(',') if args.phases else None
            )
            self.display_trials_table(filtered_trials, "Filtered Trials")
        else:
            self.display_trials_table(self.trials)
        
        if args.summary:
            self.display_ranking_summary(self.trials)


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Phase 10 Catalyst System CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Interactive mode
  %(prog)s list              # List all trials
  %(prog)s list --filter     # List with filtering
  %(prog)s evaluate          # Run automated evaluation
  %(prog)s analyze           # Run comprehensive analysis
  %(prog)s resolve           # Demonstrate LLM resolution
        """
    )
    
    parser.add_argument(
        'command',
        nargs='?',
        default='interactive',
        choices=['interactive', 'list', 'evaluate', 'analyze', 'resolve'],
        help='Command to run (default: interactive)'
    )
    
    parser.add_argument(
        '--filter',
        action='store_true',
        help='Enable filtering mode'
    )
    
    parser.add_argument(
        '--min-score',
        type=float,
        help='Minimum study card score (1-10)'
    )
    
    parser.add_argument(
        '--max-score',
        type=float,
        help='Maximum study card score (1-10)'
    )
    
    parser.add_argument(
        '--phases',
        type=str,
        help='Comma-separated list of phases (e.g., II,III)'
    )
    
    parser.add_argument(
        '--summary',
        action='store_true',
        help='Show ranking summary'
    )
    
    args = parser.parse_args()
    
    cli = CatalystCLI()
    
    try:
        if args.command == 'interactive':
            cli.run_interactive_mode()
        elif args.command == 'list':
            cli.run_list_mode(args)
        elif args.command == 'evaluate':
            cli.run_automated_evaluation()
        elif args.command == 'analyze':
            cli.run_comprehensive_analysis()
        elif args.command == 'resolve':
            cli.run_llm_resolution_demo()
    except KeyboardInterrupt:
        cli.console.print("\nGoodbye! 👋", style="green")
    except Exception as e:
        cli.console.print(f"Error: {e}", style="red")
        sys.exit(1)


if __name__ == "__main__":
    main()
