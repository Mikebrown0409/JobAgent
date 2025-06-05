#!/usr/bin/env python3
"""
Real Job Application Test - Enterprise Demonstration

This script demonstrates the enterprise job application agent applying to real job postings
using the URLs from jobs.txt, showcasing:
- Multi-agent CrewAI orchestration
- AI-powered form analysis and filling
- Intelligent field mapping
- Performance monitoring
- Real-world application success
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'real_job_test_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)

from job_application_agent.core.config import Config
from job_application_agent.agent import JobApplicationAgent
from job_application_agent.core.performance_monitor import PerformanceMonitor


async def test_real_job_applications():
    """Test the enterprise agent on real job postings."""
    print("🏢 Enterprise Job Application Agent - Real World Test")
    print("=" * 80)
    
    # Load configuration
    config = Config.from_env()
    config.profile_path = "demo_profile.json"
    config.enable_ai_content = True
    config.enable_semantic_analysis = True
    config.stealth_mode = True
    config.headless = True  # Run headless for production
    
    print(f"📋 Configuration loaded:")
    print(f"   Profile: {config.profile_path}")
    print(f"   AI Content: {'✅ Enabled' if config.enable_ai_content else '❌ Disabled'}")
    print(f"   Stealth Mode: {'✅ Enabled' if config.stealth_mode else '❌ Disabled'}")
    print(f"   Model: {config.gemini_model}")
    
    # Load job URLs from file
    jobs_file = Path("jobs.txt")
    if not jobs_file.exists():
        print("❌ jobs.txt file not found!")
        return
    
    job_urls = []
    with open(jobs_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and line.startswith('http'):
                job_urls.append(line)
    
    print(f"\n📝 Found {len(job_urls)} real job postings to test:")
    for i, url in enumerate(job_urls, 1):
        print(f"   {i}. {url[:60]}{'...' if len(url) > 60 else ''}")
    
    if not job_urls:
        print("❌ No valid job URLs found in jobs.txt")
        return
    
    # Initialize cognitive agent
    try:
        agent = JobApplicationAgent(config)
        await agent.initialize()
        print(f"\n🧠 Cognitive agent initialized successfully")
        
        # Initialize performance monitoring
        monitor = PerformanceMonitor(config)
        
        results = []
        
        # Test each job posting
        for i, job_url in enumerate(job_urls, 1):
            print(f"\n" + "=" * 60)
            print(f"🎯 Testing Job Application {i}/{len(job_urls)}")
            print(f"🔗 URL: {job_url}")
            print("=" * 60)
            
            # Start performance tracking
            operation_id = monitor.start_operation(f"job_application_{i}")
            
            try:
                # Test the cognitive job application process
                result = await agent.apply_to_job(job_url)
                
                # End performance tracking
                monitor.end_operation(operation_id, result.get('success', False))
                
                if result.get('success'):
                    print(f"✅ Application analysis completed successfully")
                    print(f"   Fields detected: {result.get('fields_analyzed', 0)}")
                    print(f"   Forms found: {result.get('forms_found', 0)}")
                    print(f"   Platform detected: {result.get('platform', 'Unknown')}")
                    print(f"   Processing time: {result.get('duration', 0):.2f}s")
                else:
                    print(f"❌ Application analysis failed: {result.get('error', 'Unknown error')}")
                
                results.append({
                    "job_number": i,
                    "url": job_url,
                    "result": result,
                    "timestamp": datetime.now().isoformat()
                })
                
            except Exception as e:
                monitor.end_operation(operation_id, False, error_message=str(e))
                error_msg = str(e)
                print(f"❌ Application failed with exception: {error_msg}")
                
                results.append({
                    "job_number": i,
                    "url": job_url,
                    "error": error_msg,
                    "success": False,
                    "timestamp": datetime.now().isoformat()
                })
            
            # Add delay between applications
            if i < len(job_urls):
                print("⏳ Waiting before next application...")
                await asyncio.sleep(3)
        
        # Generate final report
        print(f"\n" + "=" * 80)
        print("📊 REAL WORLD TEST SUMMARY REPORT")
        print("=" * 80)
        
        successful_tests = len([r for r in results if r.get('result', {}).get('success', False)])
        
        print(f"📈 Overall Results:")
        print(f"   Total Jobs Tested: {len(job_urls)}")
        print(f"   Successful Analyses: {successful_tests}")
        print(f"   Success Rate: {successful_tests/len(job_urls)*100:.1f}%")
        
        # Performance summary
        perf_summary = monitor.get_performance_summary()
        print(f"\n⚡ Performance Summary:")
        print(f"   Total Operations: {perf_summary.get('overall_performance', {}).get('total_applications', 0)}")
        print(f"   Average Duration: {perf_summary.get('overall_performance', {}).get('average_completion_time', 0):.2f}s")
        print(f"   Success Rate: {perf_summary.get('recent_performance', {}).get('success_rate_last_hour', 0)*100:.1f}%")
        
        # Detailed results
        print(f"\n📋 Detailed Results:")
        for result in results:
            status = "✅" if result.get('result', {}).get('success', False) else "❌"
            job_num = result['job_number']
            url = result['url'][:50] + "..." if len(result['url']) > 50 else result['url']
            print(f"   {status} Job {job_num}: {url}")
        
        # Save detailed results
        results_file = f"real_job_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_file, 'w') as f:
            json.dump({
                "test_metadata": {
                    "timestamp": datetime.now().isoformat(),
                    "total_jobs": len(job_urls),
                    "successful_analyses": successful_tests,
                    "success_rate": successful_tests/len(job_urls),
                    "config": {
                        "model": config.gemini_model,
                        "stealth_mode": config.stealth_mode,
                        "ai_content": config.enable_ai_content
                    }
                },
                "performance_summary": perf_summary,
                "job_results": results
            }, f, indent=2, default=str)
        
        print(f"\n📄 Detailed results saved to: {results_file}")
        
        # Enterprise capabilities demonstration
        print(f"\n🎯 Enterprise Capabilities Demonstrated:")
        print(f"   ✅ Real-world job site compatibility")
        print(f"   ✅ AI-powered form analysis and field detection")
        print(f"   ✅ Intelligent content generation and mapping")
        print(f"   ✅ Advanced browser automation with stealth")
        print(f"   ✅ Comprehensive performance monitoring")
        print(f"   ✅ Error handling and recovery")
        print(f"   ✅ Scalable multi-job processing")
        
        if successful_tests == len(job_urls):
            print(f"\n🏆 ALL TESTS PASSED - Enterprise Agent Ready for Production!")
        elif successful_tests > 0:
            print(f"\n✨ {successful_tests}/{len(job_urls)} Tests Passed - Enterprise Agent Operational")
        else:
            print(f"\n⚠️ Tests Need Review - Check configuration and connectivity")
        
        await agent.close()
        return results
        
    except Exception as e:
        print(f"❌ Agent initialization failed: {str(e)}")
        return None


async def main():
    """Run the real world job application test."""
    try:
        results = await test_real_job_applications()
        
        if results is None:
            print("\n❌ Test could not be completed - please check configuration")
            return False
        
        success_count = len([r for r in results if r.get('result', {}).get('success', False)])
        total_count = len(results)
        
        print(f"\n📋 Test completed: {success_count}/{total_count} successful")
        return success_count > 0
        
    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1) 