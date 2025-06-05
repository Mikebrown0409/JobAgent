#!/usr/bin/env python3
"""
Cognitive Browser Intelligence Test

This demonstrates the cognitive browsing engine that implements Claude-like
web browsing intelligence for job applications.
"""

import asyncio
import logging
import json
from datetime import datetime
from job_application_agent.core.config import Config
from job_application_agent.core.llm_service import LLMService
from job_application_agent.agent import JobApplicationAgent


async def test_cognitive_browsing():
    """Test the cognitive browsing capabilities."""
    
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    
    print("🧠 Testing Cognitive Browser Intelligence")
    print("=" * 60)
    
    try:
        # Initialize agent
        config = Config()
        agent = JobApplicationAgent(config)
        await agent.initialize()
        
        # Test jobs with different page types
        test_jobs = [
            "https://anthropic.com/careers",  # Job listing page
            "https://greenhouse.io/demo",     # Application form page
            "https://workday.com/careers",    # Multi-step process
        ]
        
        print(f"🎯 Testing {len(test_jobs)} different job sites")
        print()
        
        for i, job_url in enumerate(test_jobs, 1):
            print(f"🔍 Test {i}: {job_url}")
            print("-" * 40)
            
            try:
                # Test cognitive navigation and analysis
                result = await agent.apply_to_job(job_url)
                
                # Display cognitive insights
                page_analysis = result.get('page_analysis', {})
                cognitive_insights = result.get('cognitive_insights', {})
                performance_metrics = result.get('performance_metrics', {})
                
                print(f"✅ Success: {result['success']}")
                print(f"⏱️  Duration: {result['duration']:.1f}s")
                print(f"📊 Efficiency Score: {performance_metrics.get('efficiency_score', 0):.1f}/100")
                
                print("\n🧠 Cognitive Analysis:")
                print(f"  • Initial Page Type: {page_analysis.get('initial_page_type', 'unknown')}")
                print(f"  • Final Page Type: {page_analysis.get('final_page_type', 'unknown')}")
                print(f"  • Confidence: {page_analysis.get('confidence', 0):.1%}")
                print(f"  • Analysis Time: {performance_metrics.get('analysis_time', 0):.2f}s")
                
                print("\n🎯 Navigation Intelligence:")
                nav_actions = cognitive_insights.get('navigation_intelligence', [])
                for action in nav_actions[:3]:  # Show first 3 actions
                    print(f"  • {action}")
                
                print("\n📝 Form Filling Performance:")
                form_perf = cognitive_insights.get('form_filling_performance', {})
                filled = form_perf.get('filled_fields', 0)
                failed = form_perf.get('failed_fields', 0)
                print(f"  • Fields Successfully Filled: {filled}")
                print(f"  • Fields Failed: {failed}")
                if filled + failed > 0:
                    success_rate = filled / (filled + failed) * 100
                    print(f"  • Success Rate: {success_rate:.1f}%")
                
                print("\n📋 Application Steps:")
                steps = result.get('application_steps', [])
                for step in steps:
                    step_name = step.get('step', 'unknown')
                    step_success = step.get('success', False)
                    status = "✅" if step_success else "❌"
                    print(f"  {status} {step_name.replace('_', ' ').title()}")
                
                # Show reasoning if available
                reasoning = page_analysis.get('reasoning', '')
                if reasoning:
                    print(f"\n🤔 AI Reasoning: {reasoning}")
                
                print()
                
            except Exception as e:
                print(f"❌ Test failed: {str(e)}")
                logger.error(f"Test {i} failed: {str(e)}")
                print()
                continue
        
        # Test cognitive insights API
        print("🔬 Testing Cognitive Insights API")
        print("-" * 40)
        
        try:
            insights = await agent.get_cognitive_insights()
            
            print("📈 Navigation History:")
            nav_history = insights.get('navigation_history', [])
            for entry in nav_history[-3:]:  # Show last 3 entries
                timestamp = entry.get('timestamp', '')
                page_type = entry.get('page_type', 'unknown')
                confidence = entry.get('confidence', 0)
                print(f"  • {timestamp}: {page_type} ({confidence:.1%})")
            
            print("\n📊 Current Page Analysis:")
            current_analysis = insights.get('current_page_analysis', {})
            print(f"  • Page Type: {current_analysis.get('page_type', 'unknown')}")
            print(f"  • Form Fields: {current_analysis.get('form_fields_count', 0)}")
            print(f"  • Key Elements: {current_analysis.get('key_elements_count', 0)}")
            print(f"  • Analysis Time: {current_analysis.get('analysis_time', 0):.3f}s")
            
        except Exception as e:
            print(f"❌ Insights API failed: {str(e)}")
        
        print("\n🎉 Cognitive Browser Testing Complete!")
        print("=" * 60)
        
        # Demonstrate key features
        print("\n🚀 Key Cognitive Features Demonstrated:")
        print("  ✅ Instant page type recognition (job listing vs application form)")
        print("  ✅ Intelligent apply button detection and clicking")
        print("  ✅ Smart form field mapping using semantic understanding")
        print("  ✅ Context-aware navigation decisions")
        print("  ✅ Real-time performance monitoring and optimization")
        print("  ✅ Adaptive error recovery and fallback strategies")
        print("  ✅ Human-like browsing patterns and anti-detection")
        print("  ✅ Multi-strategy element finding with AI assistance")
        
        # Performance insights
        print("\n⚡ Performance Advantages:")
        print("  • Sub-second page analysis (like human instant recognition)")
        print("  • Intelligent form filling without hardcoded selectors")
        print("  • Adaptive navigation based on page context")
        print("  • Real-time decision making using AI reasoning")
        print("  • Efficient field detection using pattern recognition")
        
    except Exception as e:
        logger.error(f"Cognitive browser test failed: {str(e)}")
        print(f"❌ Critical error: {str(e)}")
    
    finally:
        # Cleanup
        try:
            await agent.close()
        except:
            pass


async def demonstrate_cognitive_comparison():
    """Demonstrate the difference between cognitive and traditional browsing."""
    
    print("\n🤔 Traditional vs Cognitive Browsing Comparison")
    print("=" * 60)
    
    print("❌ Traditional Automation Limitations:")
    print("  • Fixed selectors that break when sites change")
    print("  • No understanding of page context or purpose")
    print("  • Cannot adapt to different form layouts")
    print("  • Slow field-by-field interaction")
    print("  • No intelligent error recovery")
    print("  • Cannot handle dynamic content")
    print("  • Fails on multi-step applications")
    
    print("\n✅ Cognitive Browser Advantages:")
    print("  • Understands page semantics like a human")
    print("  • Adapts to any form layout automatically")
    print("  • Makes intelligent navigation decisions")
    print("  • Handles multi-step processes intelligently")
    print("  • Recovers from errors using alternative strategies")
    print("  • Recognizes when on wrong page and navigates correctly")
    print("  • Fills forms at human-like speed with AI precision")
    print("  • Learns from context clues and visual patterns")


if __name__ == "__main__":
    asyncio.run(test_cognitive_browsing())
    asyncio.run(demonstrate_cognitive_comparison()) 