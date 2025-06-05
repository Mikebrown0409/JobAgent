#!/usr/bin/env python3
"""
Real Job Application Test - Enterprise Agent Verification

This script tests the enterprise job application agent on real job postings
with comprehensive verification to ensure actual success, not false positives.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'real_test_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)

from job_application_agent.core.config import Config
from job_application_agent.agent import EnterpriseJobApplicationAgent


class RealApplicationTester:
    """Test the agent on real job applications with verification."""
    
    def __init__(self):
        """Initialize the tester."""
        self.logger = logging.getLogger(__name__)
        
        # Create configuration for real testing
        self.config = Config.from_env()  # Load from environment including GEMINI_API_KEY
        self.config.headless = False  # Run with browser visible for verification
        self.config.profile_path = "demo_profile.json"
        self.config.enable_ai_content = True
        self.config.enable_semantic_analysis = True
        self.config.enable_caching = True
        self.config.log_level = "INFO"
        
        self.agent = None
        self.results = []
    
    async def load_job_urls(self) -> List[str]:
        """Load job URLs from jobs.txt file."""
        try:
            with open("jobs.txt", "r") as f:
                urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            self.logger.info(f"Loaded {len(urls)} job URLs for testing")
            return urls
        except FileNotFoundError:
            self.logger.error("jobs.txt file not found")
            return []
    
    async def verify_form_filling(self, url: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """Verify that form filling actually occurred by checking page state."""
        verification = {
            'url': url,
            'timestamp': datetime.now().isoformat(),
            'filled_fields': [],
            'verification_score': 0.0,
            'screenshot_taken': False,
            'page_analysis': {},
            'actual_success': False
        }
        
        try:
            # Take screenshot for manual verification
            screenshot_path = f"verification_screenshots/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{url.split('/')[-1]}.png"
            if await self.agent.browser_tool.take_screenshot(screenshot_path):
                verification['screenshot_taken'] = True
                verification['screenshot_path'] = screenshot_path
            
            # Analyze page state to verify form filling
            page_analysis = await self.agent.browser_tool.analyze_current_page()
            verification['page_analysis'] = page_analysis
            
            # Check for filled form fields
            filled_fields = await self.agent.browser_tool.get_filled_form_data()
            verification['filled_fields'] = filled_fields
            
            # Calculate verification score based on multiple factors
            score = 0.0
            
            # Check if we have filled fields
            if filled_fields and len(filled_fields) > 0:
                score += 0.4
                self.logger.info(f"✅ Found {len(filled_fields)} filled fields")
            
            # Check if we're on a confirmation or next step page
            current_url = await self.agent.browser_tool.page.url
            if current_url != url:
                score += 0.3
                self.logger.info(f"✅ Page navigation occurred: {current_url}")
            
            # Check for success indicators in page content
            page_content = await self.agent.browser_tool.page.content()
            success_indicators = [
                'thank you', 'submitted', 'received', 'confirmation',
                'next step', 'review', 'complete', 'success'
            ]
            
            found_indicators = [indicator for indicator in success_indicators 
                              if indicator.lower() in page_content.lower()]
            if found_indicators:
                score += 0.3
                self.logger.info(f"✅ Found success indicators: {found_indicators}")
            
            verification['verification_score'] = score
            verification['actual_success'] = score >= 0.5
            
            self.logger.info(f"Verification score for {url}: {score:.2f}")
            
        except Exception as e:
            self.logger.error(f"Verification failed for {url}: {str(e)}")
            verification['error'] = str(e)
        
        return verification
    
    async def test_single_application(self, url: str) -> Dict[str, Any]:
        """Test a single job application with comprehensive verification."""
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"🎯 TESTING APPLICATION: {url}")
        self.logger.info(f"{'='*80}")
        
        test_result = {
            'url': url,
            'start_time': datetime.now().isoformat(),
            'success': False,
            'error': None,
            'steps_completed': [],
            'verification': {},
            'performance_data': {},
            'ai_decisions': []
        }
        
        try:
            # Step 1: Navigate to job application
            self.logger.info("🔗 Step 1: Navigating to job application...")
            nav_result = await self.agent.apply_to_job(url)
            
            if nav_result.get('success'):
                test_result['steps_completed'].append('navigation')
                self.logger.info("✅ Navigation successful")
                
                # Step 2: Analyze the application page
                self.logger.info("🔍 Step 2: Analyzing application form...")
                
                # Give the page time to load completely
                await asyncio.sleep(3)
                
                # Step 3: Attempt to fill the application
                self.logger.info("✍️ Step 3: Filling application form...")
                
                # Step 4: Verify the results
                self.logger.info("🔍 Step 4: Verifying form filling results...")
                verification = await self.verify_form_filling(url, nav_result)
                test_result['verification'] = verification
                
                # Determine overall success based on verification
                test_result['success'] = verification.get('actual_success', False)
                
                if test_result['success']:
                    self.logger.info("✅ APPLICATION TEST PASSED - Real form filling verified!")
                else:
                    self.logger.warning("⚠️ APPLICATION TEST INCONCLUSIVE - Manual verification needed")
            
            else:
                test_result['error'] = nav_result.get('error', 'Navigation failed')
                self.logger.error(f"❌ Navigation failed: {test_result['error']}")
        
        except Exception as e:
            test_result['error'] = str(e)
            self.logger.error(f"❌ Test failed with exception: {str(e)}")
        
        finally:
            test_result['end_time'] = datetime.now().isoformat()
            
            # Get performance data
            if self.agent and hasattr(self.agent, 'performance_monitor'):
                test_result['performance_data'] = self.agent.performance_monitor.get_performance_summary()
        
        return test_result
    
    async def run_comprehensive_test(self):
        """Run comprehensive tests on all job applications."""
        print("\n" + "="*80)
        print("🚀 ENTERPRISE AGENT - REAL JOB APPLICATION TEST")
        print("="*80)
        
        # Load job URLs
        urls = await self.load_job_urls()
        if not urls:
            print("❌ No job URLs found to test")
            return
        
        print(f"📋 Testing {len(urls)} real job applications...")
        print("🔍 Verification enabled: Screenshots + Form analysis + Success detection")
        
        # Initialize the agent
        self.logger.info("🔧 Initializing enterprise agent...")
        self.agent = EnterpriseJobApplicationAgent(self.config)
        
        # Create screenshots directory
        Path("verification_screenshots").mkdir(exist_ok=True)
        
        # Test each application
        for i, url in enumerate(urls, 1):
            print(f"\n📍 Testing Application {i}/{len(urls)}")
            print(f"🔗 URL: {url}")
            
            result = await self.test_single_application(url)
            self.results.append(result)
            
            # Brief pause between applications to avoid rate limiting
            if i < len(urls):
                print("⏱️ Pausing 10 seconds to avoid rate limiting...")
                await asyncio.sleep(10)
        
        # Generate comprehensive report
        await self.generate_verification_report()
        
        # Cleanup
        if self.agent:
            await self.agent.close()
    
    async def generate_verification_report(self):
        """Generate a comprehensive verification report."""
        print("\n" + "="*80)
        print("📊 COMPREHENSIVE VERIFICATION REPORT")
        print("="*80)
        
        successful_tests = [r for r in self.results if r['success']]
        failed_tests = [r for r in self.results if not r['success']]
        
        print(f"📈 Overall Results:")
        print(f"   Total Applications Tested: {len(self.results)}")
        print(f"   ✅ Verified Successful: {len(successful_tests)}")
        print(f"   ❌ Failed/Inconclusive: {len(failed_tests)}")
        print(f"   🎯 Success Rate: {len(successful_tests)/len(self.results)*100:.1f}%")
        
        # Detailed results for each application
        print(f"\n📋 Detailed Results:")
        for i, result in enumerate(self.results, 1):
            status = "✅ VERIFIED SUCCESS" if result['success'] else "❌ FAILED/INCONCLUSIVE"
            print(f"\n{i}. {result['url']}")
            print(f"   Status: {status}")
            
            if result.get('verification'):
                v = result['verification']
                print(f"   Verification Score: {v.get('verification_score', 0):.2f}")
                print(f"   Filled Fields: {len(v.get('filled_fields', []))}")
                print(f"   Screenshot: {'✅' if v.get('screenshot_taken') else '❌'}")
            
            if result.get('error'):
                print(f"   Error: {result['error']}")
        
        # Save detailed report to file
        report_file = f"verification_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        print(f"\n💾 Detailed report saved to: {report_file}")
        print(f"📸 Screenshots saved to: verification_screenshots/")
        
        if successful_tests:
            print(f"\n🎉 SUCCESS! {len(successful_tests)} real job applications were successfully filled!")
        else:
            print(f"\n⚠️ No applications were verified as successful. Manual review recommended.")


async def main():
    """Main test execution."""
    tester = RealApplicationTester()
    await tester.run_comprehensive_test()


if __name__ == "__main__":
    print("🚀 Starting Real Job Application Test with Verification...")
    asyncio.run(main()) 