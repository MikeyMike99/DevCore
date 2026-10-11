import asyncio, agent_manager
async def test():
    am = agent_manager.AgentTaskManager()
    await am.start_task('test', admin_override=True)
    if hasattr(am, 'active_task') and am.active_task:
        await am.active_task
asyncio.run(test())
