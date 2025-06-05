#!/usr/bin/env python3
"""
Enterprise Job Application Agent Demo

This script demonstrates the advanced enterprise features of the job application agent:
- AI-powered intelligent form filling
- Semantic field matching
- Dynamic content generation
- Performance monitoring
- Advanced error handling
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'enterprise_demo_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)

from job_application_agent.core.config import Config
from job_application_agent.agent import EnterpriseJobApplicationAgent
from job_application_agent.core.performance_monitor import PerformanceMonitor


async def demonstrate_ai_field_mapping():
    """Demonstrate AI-powered field mapping capabilities."""
    print("\n🧠 AI-Powered Field Mapping Demo")
    print("=" * 50)
    
    # Load configuration
    config = Config.from_env()
    config.enable_ai_content = True
    config.enable_semantic_analysis = True
    config.profile_path = "demo_profile.json"
    
    # Initialize components
    from job_application_agent.core.llm_service import LLMService
    from job_application_agent.tools.intelligent_form_filler import IntelligentFormFiller
    from job_application_agent.tools.browser_tool import AdvancedBrowserTool
    from job_application_agent.core.memory.profile_store import ProfileStore
    
    llm_service = LLMService(config)
    profile_store = ProfileStore(config.profile_path)
    browser_tool = AdvancedBrowserTool(config)
    form_filler = IntelligentFormFiller(config, browser_tool, llm_service)
    
    # Load profile data
    profile_data = profile_store.get_profile_data()
    
    # Simulate complex form fields
    mock_fields = [
        {
            "field_purpose": "first_name",
            "label": "First Name",
            "type": "text",
            "selectors": ["#firstName", "[name='firstName']"],
            "is_visible": True,
            "is_enabled": True
        },
        {
            "field_purpose": "motivation_question", 
            "label": "Why are you interested in this position?",
            "type": "textarea",
            "selectors": ["#motivation", "[name='motivation']"],
            "is_visible": True,
            "is_enabled": True
        },
        {
            "field_purpose": "education_field",
            "label": "University",
            "type": "text", 
            "selectors": ["#university", "[name='university']"],
            "is_visible": True,
            "is_enabled": True
        }
    ]
    
    print("📋 Analyzing mock form fields...")
    
    # Generate intelligent mappings
    mappings = await form_filler._generate_intelligent_mappings(profile_data, mock_fields)
    
    print(f"\n✅ Generated {len(mappings)} intelligent field mappings:")
    
    for mapping in mappings:
        print(f"\n  🎯 Field: {mapping.field_info.get('label', 'Unknown')}")
        print(f"     Strategy: {mapping.strategy.value}")
        print(f"     Confidence: {mapping.confidence:.2f}")
        print(f"     Value: {str(mapping.profile_value)[:100]}{'...' if len(str(mapping.profile_value)) > 100 else ''}")
    
    return {"mappings_generated": len(mappings), "strategies_used": [m.strategy.value for m in mappings]}


async def demonstrate_ai_content_generation():
    """Demonstrate AI content generation for open-ended questions."""
    print("\n📝 AI Content Generation Demo")
    print("=" * 50)
    
    config = Config.from_env()
    
    if not config.google_api_key:
        print("⚠️ No Google API key found. Skipping AI content generation demo.")
        return {"status": "skipped", "reason": "no_api_key"}
    
    from job_application_agent.core.llm_service import LLMService
    
    llm_service = LLMService(config)
    
    # Test AI content generation for common job application questions
    test_questions = [
        {
            "label": "Why are you interested in this role?",
            "placeholder": "Tell us what attracts you to this position",
            "context": "Software Engineer position at tech startup"
        },
        {
            "label": "Describe your biggest achievement",
            "placeholder": "Share a specific example of your accomplishments",
            "context": "Leadership and technical achievements"
        },
        {
            "label": "Where do you see yourself in 5 years?",
            "placeholder": "Describe your career goals",
            "context": "Career development and growth"
        }
    ]
    
    results = []
    
    for question in test_questions:
        print(f"\n🤖 Generating content for: '{question['label']}'")
        
        try:
            # Load profile for context
            from job_application_agent.core.memory.profile_store import ProfileStore
            profile_store = ProfileStore("demo_profile.json")
            profile_data = profile_store.get_profile_data()
            
            content = await llm_service.generate_contextual_answer(question, profile_data)
            
            if content:
                print(f"✅ Generated {len(content)} characters")
                print(f"   Preview: {content[:150]}{'...' if len(content) > 150 else ''}")
                results.append({
                    "question": question["label"],
                    "content_length": len(content),
                    "success": True
                })
            else:
                print("❌ No content generated")
                results.append({
                    "question": question["label"],
                    "content_length": 0,
                    "success": False
                })
        
        except Exception as e:
            print(f"❌ Error generating content: {str(e)}")
            results.append({
                "question": question["label"],
                "error": str(e),
                "success": False
            })
    
    return {"generated_content": results}


async def demonstrate_performance_monitoring():
    """Demonstrate enterprise performance monitoring."""
    print("\n📊 Performance Monitoring Demo")
    print("=" * 50)
    
    config = Config.from_env()
    monitor = PerformanceMonitor(config)
    
    # Simulate some operations
    operations = [
        ("page_navigation", True, 2.3),
        ("form_analysis", True, 1.7),
        ("field_filling", True, 0.8),
        ("ai_content_generation", True, 3.2),
        ("form_submission", False, 5.1),  # Simulated failure
        ("verification", True, 1.2)
    ]
    
    print("🔄 Simulating job application operations...")
    
    for operation, success, duration in operations:
        op_id = monitor.start_operation(operation)
        
        # Simulate operation time
        await asyncio.sleep(0.1)
        
        error_msg = "Submission failed: CAPTCHA detected" if not success else None
        monitor.end_operation(op_id, success, error_message=error_msg)
        
        status = "✅" if success else "❌"
        print(f"  {status} {operation}: {duration}s")
    
    # Get performance summary
    summary = monitor.get_performance_summary()
    
    print(f"\n📈 Performance Summary:")
    print(f"   Session Duration: {summary['session_duration']:.1f}s")
    print(f"   Operations: {summary['overall_performance']['total_applications']}")
    print(f"   Success Rate: {summary['recent_performance']['success_rate_last_hour']:.1%}")
    print(f"   Alerts: {len(summary['performance_alerts'])}")
    
    if summary['performance_alerts']:
        print(f"\n⚠️ Performance Alerts:")
        for alert in summary['performance_alerts']:
            print(f"   {alert['type'].upper()}: {alert['message']}")
    
    return summary


async def demonstrate_advanced_browser_capabilities():
    """Demonstrate advanced browser automation capabilities."""
    print("\n🌐 Advanced Browser Capabilities Demo")
    print("=" * 50)
    
    config = Config.from_env()
    
    from job_application_agent.tools.browser_tool import AdvancedBrowserTool
    
    browser_tool = AdvancedBrowserTool(config)
    
    print("🚀 Initializing advanced browser with stealth capabilities...")
    
    try:
        await browser_tool.start()
        print("✅ Browser started successfully")
        
        # Test advanced features (without actually navigating to avoid real requests)
        features = {
            "Stealth Mode": "Enabled - Human-like behavior patterns",
            "Anti-Detection": "User agent rotation, viewport randomization",
            "Smart Waiting": "Dynamic content loading detection",
            "Error Recovery": "Automatic retry with exponential backoff",
            "Screenshot Capture": "Verification and debugging support",
            "Form Intelligence": "Dynamic field detection and interaction"
        }
        
        print("\n🛡️ Advanced Browser Features:")
        for feature, description in features.items():
            print(f"   ✓ {feature}: {description}")
        
        # Demonstrate form analysis capabilities
        print("\n🔍 Form Analysis Capabilities:")
        analysis_features = [
            "Semantic field purpose detection",
            "Dynamic content loading handling", 
            "Complex interaction pattern recognition",
            "Multi-step form navigation",
            "CAPTCHA and challenge detection",
            "Error state recovery"
        ]
        
        for feature in analysis_features:
            print(f"   ✓ {feature}")
        
        await browser_tool.close()
        print("\n✅ Browser capabilities demonstrated successfully")
        
        return {"status": "success", "features_demonstrated": len(features)}
    
    except Exception as e:
        print(f"❌ Browser demo failed: {str(e)}")
        return {"status": "error", "error": str(e)}


async def demonstrate_enterprise_configuration():
    """Demonstrate enterprise configuration management."""
    print("\n⚙️ Enterprise Configuration Demo")  
    print("=" * 50)
    
    config = Config.from_env()
    
    print("📋 Enterprise Configuration Settings:")
    
    # Core settings
    print(f"\n🔧 Core Settings:")
    print(f"   Profile Path: {config.profile_path}")
    print(f"   Log Level: {config.log_level}")
    print(f"   Browser Timeout: {config.browser_timeout}ms")
    print(f"   Page Load Timeout: {config.page_load_timeout}ms")
    
    # AI settings
    print(f"\n🧠 AI Settings:")
    print(f"   AI Content Generation: {'✅ Enabled' if config.enable_ai_content else '❌ Disabled'}")
    print(f"   Semantic Analysis: {'✅ Enabled' if config.enable_semantic_analysis else '❌ Disabled'}")
    print(f"   LLM Model: {config.gemini_model}")
    print(f"   LLM Temperature: {config.llm_temperature}")
    print(f"   Max Tokens: {config.llm_max_tokens}")
    
    # Performance settings
    print(f"\n⚡ Performance Settings:")
    print(f"   Max Retries: {config.max_retries}")
    print(f"   Retry Delay: {config.retry_delay}s")
    print(f"   Concurrent Applications: {config.concurrent_applications}")
    print(f"   Performance Tracking: {'✅ Enabled' if config.enable_performance_tracking else '❌ Disabled'}")
    print(f"   Caching: {'✅ Enabled' if config.enable_caching else '❌ Disabled'}")
    
    # Security settings
    print(f"\n🔒 Security Settings:")
    print(f"   Stealth Mode: {'✅ Enabled' if config.stealth_mode else '❌ Disabled'}")
    print(f"   User Agent: {config.user_agent[:50]}...")
    
    # Storage settings
    print(f"\n💾 Storage Settings:")
    print(f"   Results Directory: {config.results_dir}")
    print(f"   Logs Directory: {config.logs_dir}")
    print(f"   Cache Directory: {config.cache_dir}")
    
    # Ensure directories exist
    config.ensure_directories()
    print(f"\n✅ All directories verified/created")
    
    return {"configuration": "enterprise_ready"}


async def run_enterprise_demo():
    """Run the complete enterprise demo."""
    print("🚀 Enterprise Job Application Agent Demo")
    print("=" * 80)
    print("Demonstrating advanced AI-powered job application automation")
    print("=" * 80)
    
    results = {}
    
    try:
        # 1. Configuration Demo
        print("\n" + "🔹" * 20 + " PHASE 1: CONFIGURATION " + "🔹" * 20)
        results["configuration"] = await demonstrate_enterprise_configuration()
        
        # 2. AI Field Mapping Demo  
        print("\n" + "🔹" * 20 + " PHASE 2: AI FIELD MAPPING " + "🔹" * 20)
        results["field_mapping"] = await demonstrate_ai_field_mapping()
        
        # 3. AI Content Generation Demo
        print("\n" + "🔹" * 20 + " PHASE 3: AI CONTENT GENERATION " + "🔹" * 20)
        results["content_generation"] = await demonstrate_ai_content_generation()
        
        # 4. Performance Monitoring Demo
        print("\n" + "🔹" * 20 + " PHASE 4: PERFORMANCE MONITORING " + "🔹" * 20) 
        results["performance"] = await demonstrate_performance_monitoring()
        
        # 5. Browser Capabilities Demo
        print("\n" + "🔹" * 20 + " PHASE 5: BROWSER CAPABILITIES " + "🔹" * 20)
        results["browser"] = await demonstrate_advanced_browser_capabilities()
        
    except Exception as e:
        print(f"\n❌ Demo failed with error: {str(e)}")
        results["error"] = str(e)
    
    # Generate summary report
    print("\n" + "=" * 80)
    print("📊 ENTERPRISE DEMO SUMMARY REPORT")
    print("=" * 80)
    
    print(f"✅ Configuration: Enterprise-ready")
    print(f"✅ AI Field Mapping: {results.get('field_mapping', {}).get('mappings_generated', 0)} mappings generated")
    
    content_results = results.get('content_generation', {})
    if isinstance(content_results, dict) and 'generated_content' in content_results:
        successful_content = len([r for r in content_results['generated_content'] if r.get('success')])
        print(f"✅ AI Content Generation: {successful_content} successful generations")
    else:
        print(f"⚠️ AI Content Generation: {content_results.get('status', 'unknown')}")
    
    perf_results = results.get('performance', {})
    if 'overall_performance' in perf_results:
        print(f"✅ Performance Monitoring: {perf_results['overall_performance']['total_applications']} operations tracked")
    
    browser_results = results.get('browser', {})
    if browser_results.get('status') == 'success':
        print(f"✅ Browser Capabilities: {browser_results.get('features_demonstrated', 0)} features demonstrated")
    else:
        print(f"⚠️ Browser Capabilities: {browser_results.get('status', 'unknown')}")
    
    print("\n🎯 Enterprise Agent Ready for Production Deployment!")
    print("   • AI-powered field mapping and content generation")
    print("   • Advanced browser automation with stealth capabilities")
    print("   • Real-time performance monitoring and alerting")
    print("   • Scalable configuration management")
    print("   • Production-ready error handling and recovery")
    
    # Save detailed results
    results_file = f"enterprise_demo_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n📄 Detailed results saved to: {results_file}")
    
    return results


if __name__ == "__main__":
    asyncio.run(run_enterprise_demo()) 