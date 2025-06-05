"""
Enterprise Job Application Agent - Main Entry Point

Command-line interface for the enterprise-grade AI job application agent.
Supports advanced features, configuration management, and comprehensive logging.
"""

import asyncio
import argparse
import sys
import json
from pathlib import Path
from typing import Optional, Dict, Any

from job_application_agent.core.config import Config
from job_application_agent.agent import EnterpriseJobApplicationAgent
from job_application_agent.utils.logging_setup import setup_logging


async def apply_to_single_job(agent: EnterpriseJobApplicationAgent, job_url: str, 
                            additional_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Apply to a single job."""
    try:
        result = await agent.apply_to_job(job_url, additional_context)
        return result
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'job_url': job_url
        }


async def apply_to_multiple_jobs(agent: EnterpriseJobApplicationAgent, 
                               job_urls: list[str]) -> Dict[str, Any]:
    """Apply to multiple jobs concurrently."""
    results = []
    
    # Apply to jobs with controlled concurrency
    semaphore = asyncio.Semaphore(agent.config.concurrent_applications)
    
    async def apply_with_semaphore(url: str) -> Dict[str, Any]:
        async with semaphore:
            return await apply_to_single_job(agent, url)
    
    # Execute applications
    tasks = [apply_with_semaphore(url) for url in job_urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results
    successful_applications = []
    failed_applications = []
    
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            failed_applications.append({
                'job_url': job_urls[i],
                'error': str(result),
                'success': False
            })
        elif result.get('success'):
            successful_applications.append(result)
        else:
            failed_applications.append(result)
    
    return {
        'total_jobs': len(job_urls),
        'successful_applications': len(successful_applications),
        'failed_applications': len(failed_applications),
        'success_rate': len(successful_applications) / len(job_urls) if job_urls else 0,
        'results': {
            'successful': successful_applications,
            'failed': failed_applications
        }
    }


def save_results(results: Dict[str, Any], output_file: Optional[str] = None) -> None:
    """Save results to file."""
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"Results saved to: {output_path}")


def print_summary(results: Dict[str, Any]) -> None:
    """Print application summary."""
    if 'total_jobs' in results:
        # Multiple jobs summary
        print("\n" + "="*60)
        print("JOB APPLICATION SUMMARY")
        print("="*60)
        print(f"Total Jobs: {results['total_jobs']}")
        print(f"Successful Applications: {results['successful_applications']}")
        print(f"Failed Applications: {results['failed_applications']}")
        print(f"Success Rate: {results['success_rate']:.1%}")
        
        if results['results']['failed']:
            print("\nFailed Applications:")
            for failed in results['results']['failed']:
                print(f"  - {failed.get('job_url', 'Unknown')}: {failed.get('error', 'Unknown error')}")
    
    else:
        # Single job summary
        print("\n" + "="*60)
        print("JOB APPLICATION RESULT")
        print("="*60)
        print(f"Job URL: {results.get('job_url', 'Unknown')}")
        print(f"Success: {'✓' if results.get('success') else '✗'}")
        
        if results.get('success'):
            summary = results.get('summary', {})
            print(f"Duration: {results.get('duration_seconds', 0):.1f} seconds")
            print(f"Fields Filled: {summary.get('successful_fills', 0)}")
            print(f"Success Rate: {summary.get('success_rate', 0):.1%}")
        else:
            print(f"Error: {results.get('error', 'Unknown error')}")
        
        # Print recommendations
        recommendations = results.get('recommendations', [])
        if recommendations:
            print("\nRecommendations:")
            for rec in recommendations:
                print(f"  - {rec}")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Enterprise Job Application Agent - AI-Powered Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Apply to a single job
  python -m job_application_agent.main --url "https://company.com/jobs/123"
  
  # Apply to multiple jobs from file
  python -m job_application_agent.main --urls-file jobs.txt
  
  # Apply with custom configuration
  python -m job_application_agent.main --url "https://company.com/jobs/123" --config config.json
  
  # Apply with additional context
  python -m job_application_agent.main --url "https://company.com/jobs/123" --context '{"company": "TechCorp", "role": "Software Engineer"}'
  
Environment Variables:
  JOB_AGENT_GOOGLE_API_KEY     Google API key for AI features
  JOB_AGENT_HEADLESS           Run browser in headless mode (true/false)
  JOB_AGENT_RESUME_PATH        Path to resume file
  JOB_AGENT_COVER_LETTER_PATH  Path to cover letter file
  JOB_AGENT_LOG_LEVEL          Logging level (DEBUG, INFO, WARNING, ERROR)
        """
    )
    
    # Job specification
    job_group = parser.add_mutually_exclusive_group(required=True)
    job_group.add_argument(
        '--url', '-u',
        help='Single job application URL'
    )
    job_group.add_argument(
        '--urls', '-U',
        nargs='+',
        help='Multiple job application URLs'
    )
    job_group.add_argument(
        '--urls-file', '-f',
        help='File containing job URLs (one per line)'
    )
    
    # Configuration
    parser.add_argument(
        '--config', '-c',
        help='Path to configuration file (JSON)'
    )
    parser.add_argument(
        '--profile', '-p',
        help='Path to user profile file (JSON)'
    )
    parser.add_argument(
        '--context',
        help='Additional context as JSON string'
    )
    
    # Output options
    parser.add_argument(
        '--output', '-o',
        help='Output file for results (JSON)'
    )
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Suppress output except errors'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    # Browser options
    parser.add_argument(
        '--headless',
        action='store_true',
        help='Run browser in headless mode'
    )
    parser.add_argument(
        '--no-headless',
        action='store_true',
        help='Run browser with GUI (overrides headless)'
    )
    
    # AI options
    parser.add_argument(
        '--no-ai',
        action='store_true',
        help='Disable AI features'
    )
    parser.add_argument(
        '--api-key',
        help='Google API key for AI features'
    )
    
    args = parser.parse_args()
    
    try:
        # Load configuration
        if args.config:
            with open(args.config, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            config = Config(**config_data)
        else:
            config = Config.from_env()
        
        # Override configuration with command line arguments
        if args.profile:
            config.profile_path = args.profile
        if args.headless:
            config.headless = True
        if args.no_headless:
            config.headless = False
        if args.no_ai:
            config.enable_ai_content = False
            config.enable_semantic_analysis = False
        if args.api_key:
            config.google_api_key = args.api_key
        if args.verbose:
            config.log_level = 'DEBUG'
        elif args.quiet:
            config.log_level = 'ERROR'
        
        # Ensure directories exist
        config.ensure_directories()
        
        # Setup logging
        setup_logging(config)
        
        # Parse additional context
        additional_context = None
        if args.context:
            try:
                additional_context = json.loads(args.context)
            except json.JSONDecodeError as e:
                print(f"Error parsing context JSON: {e}", file=sys.stderr)
                return 1
        
        # Determine job URLs
        job_urls = []
        if args.url:
            job_urls = [args.url]
        elif args.urls:
            job_urls = args.urls
        elif args.urls_file:
            urls_file = Path(args.urls_file)
            if not urls_file.exists():
                print(f"Error: URLs file not found: {urls_file}", file=sys.stderr)
                return 1
            
            with open(urls_file, 'r', encoding='utf-8') as f:
                job_urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        if not job_urls:
            print("Error: No job URLs provided", file=sys.stderr)
            return 1
        
        # Validate configuration
        if config.enable_ai_content and not config.is_ai_enabled():
            print("Warning: AI features enabled but no API key provided. AI features will be disabled.")
            config.enable_ai_content = False
            config.enable_semantic_analysis = False
        
        if not args.quiet:
            print(f"Enterprise Job Application Agent")
            print(f"Jobs to process: {len(job_urls)}")
            print(f"AI features: {'Enabled' if config.is_ai_enabled() else 'Disabled'}")
            print(f"Headless mode: {config.headless}")
            print(f"Profile: {config.profile_path}")
            print()
        
        # Initialize and run agent
        agent = EnterpriseJobApplicationAgent(config)
        
        try:
            if len(job_urls) == 1:
                # Single job application
                results = await apply_to_single_job(agent, job_urls[0], additional_context)
            else:
                # Multiple job applications
                results = await apply_to_multiple_jobs(agent, job_urls)
            
            # Save results
            if args.output:
                save_results(results, args.output)
            
            # Print summary
            if not args.quiet:
                print_summary(results)
            
            # Determine exit code
            if isinstance(results, dict):
                if 'total_jobs' in results:
                    # Multiple jobs
                    return 0 if results['successful_applications'] > 0 else 1
                else:
                    # Single job
                    return 0 if results.get('success') else 1
            
            return 1
            
        finally:
            await agent.close()
    
    except KeyboardInterrupt:
        print("\nApplication interrupted by user", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main())) 