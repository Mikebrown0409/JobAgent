"""
Test script for enhanced cognitive browsing capabilities.

Tests the Claude-like browsing intelligence with aggressive timeout prevention
and multiple fallback strategies.
"""

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path

from job_application_agent.agent import JobApplicationAgent
from job_application_agent.core.config import Config

# Configure logging for detailed insights
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('cognitive_enhancement_test.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Test job URLs that often cause timeouts (now should work with cognitive intelligence)
CHALLENGING_JOB_URLS = [
    {
        'url': 'https://therundown.ai/careers',
        'name': 'TheRundown.ai - Multi-step application',
        'expected_challenges': ['multi-step forms', 'custom fields', 'file uploads']
    },
    {
        'url': 'https://boards.greenhouse.io/embed/job_app?for=allscripts&token=6546965003',
        'name': 'Allscripts - Greenhouse application',
        'expected_challenges': ['iframe forms', 'dynamic loading', 'validation']
    },
    {
        'url': 'https://job-boards.greenhouse.io/remotecom/jobs/6568950003',
        'name': 'Remote.com - Greenhouse job board',
        'expected_challenges': ['redirect handling', 'form detection']
    },
    {
        'url': 'https://lever.co/missionlane/e8e7f8e4-2a3b-4b3c-9c5d-1e2f3a4b5c6d',
        'name': 'Mission Lane - Lever application',
        'expected_challenges': ['SPA navigation', 'async form loading']
    }
]

class CognitiveEnhancementTester:
    """Test the enhanced cognitive browsing capabilities."""
    
    def __init__(self):
        self.config = Config()
        self.agent = None
        self.results = []
        
    async def run_comprehensive_test(self):
        """Run comprehensive test of cognitive enhancements."""
        
        logger.info("🧠 Starting Cognitive Enhancement Test Suite")
        logger.info("=" * 70)
        
        try:
            # Initialize agent
            await self._initialize_agent()
            
            # Test each challenging job URL
            for i, job_test in enumerate(CHALLENGING_JOB_URLS, 1):
                await self._test_cognitive_application(i, job_test)
                
                # Brief pause between tests
                if i < len(CHALLENGING_JOB_URLS):
                    logger.info("⏳ Pausing between tests...")
                    await asyncio.sleep(2)
            
            # Analyze results
            await self._analyze_test_results()
            
        except Exception as e:
            logger.error(f"❌ Test suite failed: {str(e)}")
        finally:
            await self._cleanup()
    
    async def _initialize_agent(self):
        """Initialize the job application agent."""
        
        logger.info("🚀 Initializing Enhanced Cognitive Agent...")
        
        self.agent = JobApplicationAgent(self.config)
        await self.agent.start()
        
        logger.info("✅ Agent initialized with cognitive browsing capabilities")
        
    async def _test_cognitive_application(self, test_number: int, job_test: dict):
        """Test cognitive application on a specific job."""
        
        url = job_test['url']
        name = job_test['name']
        challenges = job_test['expected_challenges']
        
        logger.info("=" * 70)
        logger.info(f"🎯 Test {test_number}/{len(CHALLENGING_JOB_URLS)}: {name}")
        logger.info(f"🔗 URL: {url}")
        logger.info(f"🧩 Expected Challenges: {', '.join(challenges)}")
        logger.info("=" * 70)
        
        start_time = time.time()
        result = {
            'test_number': test_number,
            'name': name,
            'url': url,
            'expected_challenges': challenges,
            'start_time': start_time,
            'success': False,
            'error': None,
            'duration': 0,
            'cognitive_insights': {},
            'performance_metrics': {}
        }
        
        try:
            # Apply with cognitive intelligence
            logger.info("🤖 Starting cognitive job application...")
            
            application_result = await asyncio.wait_for(
                self.agent.apply_to_job(url),
                timeout=60  # 1 minute max per application (Claude-like efficiency)
            )
            
            end_time = time.time()
            duration = end_time - start_time
            
            result.update({
                'success': application_result.get('success', False),
                'duration': duration,
                'cognitive_insights': application_result.get('cognitive_insights', {}),
                'performance_metrics': application_result.get('performance_metrics', {}),
                'steps_taken': application_result.get('steps_taken', 0),
                'form_fields_filled': application_result.get('form_fields_filled', 0),
                'page_analysis_time': application_result.get('page_analysis_time', 0)
            })
            
            # Log detailed results
            if result['success']:
                logger.info(f"✅ Application completed successfully in {duration:.2f}s")
                logger.info(f"📊 Steps taken: {result.get('steps_taken', 0)}")
                logger.info(f"📝 Fields filled: {result.get('form_fields_filled', 0)}")
                logger.info(f"⚡ Page analysis: {result.get('page_analysis_time', 0):.2f}s")
            else:
                logger.warning(f"⚠️ Application completed with issues in {duration:.2f}s")
                
        except asyncio.TimeoutError:
            duration = time.time() - start_time
            result.update({
                'error': 'Application timed out after 60 seconds',
                'duration': duration
            })
            logger.error(f"⏰ Application timed out after {duration:.2f}s")
            
        except Exception as e:
            duration = time.time() - start_time
            result.update({
                'error': str(e),
                'duration': duration
            })
            logger.error(f"❌ Application failed: {str(e)}")
        
        self.results.append(result)
        
        # Log cognitive insights if available
        if result.get('cognitive_insights'):
            insights = result['cognitive_insights']
            logger.info("🧠 Cognitive Insights:")
            for key, value in insights.items():
                logger.info(f"  • {key}: {value}")
    
    async def _analyze_test_results(self):
        """Analyze and report test results."""
        
        logger.info("=" * 70)
        logger.info("📊 COGNITIVE ENHANCEMENT TEST RESULTS")
        logger.info("=" * 70)
        
        # Overall statistics
        total_tests = len(self.results)
        successful_tests = len([r for r in self.results if r['success']])
        success_rate = (successful_tests / total_tests * 100) if total_tests > 0 else 0
        
        total_duration = sum(r['duration'] for r in self.results)
        avg_duration = total_duration / total_tests if total_tests > 0 else 0
        
        logger.info(f"🎯 Overall Success Rate: {success_rate:.1f}% ({successful_tests}/{total_tests})")
        logger.info(f"⏱️ Average Application Time: {avg_duration:.2f}s")
        logger.info(f"🕐 Total Test Duration: {total_duration:.2f}s")
        
        # Detailed results
        logger.info("\n📋 Detailed Results:")
        for result in self.results:
            status = "✅ SUCCESS" if result['success'] else "❌ FAILED"
            duration = result['duration']
            
            logger.info(f"\n  {result['test_number']}. {result['name']}")
            logger.info(f"     Status: {status}")
            logger.info(f"     Duration: {duration:.2f}s")
            
            if result['error']:
                logger.info(f"     Error: {result['error']}")
            
            if result.get('steps_taken'):
                logger.info(f"     Steps: {result['steps_taken']}")
                
            if result.get('form_fields_filled'):
                logger.info(f"     Fields: {result['form_fields_filled']}")
        
        # Performance analysis
        logger.info("\n⚡ Performance Analysis:")
        fast_applications = [r for r in self.results if r['duration'] < 30]
        slow_applications = [r for r in self.results if r['duration'] >= 30]
        
        logger.info(f"  • Fast applications (<30s): {len(fast_applications)}")
        logger.info(f"  • Slow applications (≥30s): {len(slow_applications)}")
        
        if self.results:
            fastest = min(self.results, key=lambda x: x['duration'])
            slowest = max(self.results, key=lambda x: x['duration'])
            
            logger.info(f"  • Fastest: {fastest['name']} - {fastest['duration']:.2f}s")
            logger.info(f"  • Slowest: {slowest['name']} - {slowest['duration']:.2f}s")
        
        # Save results
        await self._save_test_results()
        
        # Final assessment
        logger.info("\n🎨 COGNITIVE ENHANCEMENT ASSESSMENT:")
        if success_rate >= 80:
            logger.info("🌟 EXCELLENT: Cognitive browsing is working at Claude level!")
        elif success_rate >= 60:
            logger.info("👍 GOOD: Significant improvement, some fine-tuning needed")
        elif success_rate >= 40:
            logger.info("⚠️ MODERATE: Basic cognitive features working, needs enhancement")
        else:
            logger.info("🔧 NEEDS WORK: Cognitive features need significant improvement")
        
        if avg_duration <= 30:
            logger.info("⚡ SPEED: Excellent - Claude-like efficiency achieved!")
        elif avg_duration <= 60:
            logger.info("🏃 SPEED: Good - Within acceptable range")
        else:
            logger.info("🐌 SPEED: Needs optimization - too slow for production use")
    
    async def _save_test_results(self):
        """Save test results to file."""
        
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            results_file = Path(f"cognitive_enhancement_results_{timestamp}.json")
            
            import json
            with open(results_file, 'w') as f:
                json.dump({
                    'test_timestamp': timestamp,
                    'test_summary': {
                        'total_tests': len(self.results),
                        'successful_tests': len([r for r in self.results if r['success']]),
                        'success_rate': len([r for r in self.results if r['success']]) / len(self.results) * 100 if self.results else 0,
                        'average_duration': sum(r['duration'] for r in self.results) / len(self.results) if self.results else 0
                    },
                    'detailed_results': self.results
                }, f, indent=2, default=str)
            
            logger.info(f"💾 Test results saved to: {results_file}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save results: {str(e)}")
    
    async def _cleanup(self):
        """Clean up resources."""
        
        if self.agent:
            try:
                await self.agent.stop()
                logger.info("🧹 Agent stopped and resources cleaned up")
            except Exception as e:
                logger.error(f"❌ Error during cleanup: {str(e)}")

async def main():
    """Run the cognitive enhancement test suite."""
    
    tester = CognitiveEnhancementTester()
    await tester.run_comprehensive_test()

if __name__ == "__main__":
    asyncio.run(main()) 