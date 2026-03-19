#!/usr/bin/env python3
"""Manually dispatch stuck upload to Celery worker."""
import asyncio
import time
import sys
from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.tasks.uploads import process_upload_task

async def main():
    async with AsyncSessionLocal() as db:
        # Get the stuck Sales upload
        result = await db.execute(text("""
            SELECT u.id, b.id FROM uploads u
            JOIN brands b ON u.brand_id = b.id
            WHERE u.filename LIKE '%SALES HISTORY%'
        """))
        row = result.fetchone()
        if not row:
            print("❌ Sales History upload not found!")
            return
        
        upload_id, brand_id = row
        print(f"✅ Found upload")
        print(f"   Upload ID: {upload_id}")
        print(f"   Brand ID: {brand_id}")
    
    # Dispatch the task
    print("\n📤 Dispatching task to Celery...")
    task = process_upload_task.apply_async(args=[str(upload_id), str(brand_id)])
    print(f"   Task ID: {task.id}")
    print(f"   Initial state: {task.state}")
    
    # Monitor task state
    print("\n⏳ Monitoring task state...")
    for i in range(60):
        state = task.state
        status = f"[{i+1:2d}s] State: {state:10s}"
        if state == 'PENDING':
            print(f"{status}", end='\r')
        elif state == 'STARTED':
            print(f"{status} ⚙️ ")
        elif state == 'SUCCESS':
            print(f"{status} ✅")
            # Get the actual result 
            await asyncio.sleep(1)
            async with AsyncSessionLocal() as db:
                result = await db.execute(text("""
                    SELECT status, total_rows, successful_rows, failed_rows 
                    FROM uploads WHERE id = %s
                """), [upload_id])
                u_status, total, success, failed = result.fetchone()
                print(f"   Upload status: {u_status}")
                print(f"   Rows: {success}/{total} ✅, {failed} ❌")
            break
        elif state == 'FAILURE':
            print(f"{status} ❌")
            print(f"   Error: {task.info}")
            break
        else:
            print(f"{status}")
        await asyncio.sleep(1)
    else:
        print("\n⚠️  Task did not complete within 60 seconds")

if __name__ == '__main__':
    asyncio.run(main())
