import os
import boto3
import logging
import json
import time

"""
Transit Gateway Attachment 制御用 Lambda関数
用途: プロジェクト凍結時のコスト削減（$47/月 ⇔ $0）

パラメータ:
  event['action']: 'remove' (削除) または 'add' (作成)
"""

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 環境変数から設定を取得
TGW_ID = os.environ.get('TGW_ID', '')
VPC_ID = os.environ.get('VPC_ID', '')
SUBNET_IDS = os.environ.get('SUBNET_IDS', '')
TAG_NAME = os.environ.get('TAG_NAME', 'v2-tgwa-test-magent')
TGW_ATTACHMENT_ID = os.environ.get('TGW_ATTACHMENT_ID', '')

client = boto3.client('ec2')

# ==================== 共通処理 ====================

def get_attachment_info(attachment_id):
    """Transit Gateway Attachmentの情報を取得"""
    logger.info(f'Attachment情報取得: {attachment_id}')
    
    response = client.describe_transit_gateway_vpc_attachments(
        TransitGatewayAttachmentIds=[attachment_id]
    )
    
    if not response['TransitGatewayVpcAttachments']:
        raise Exception(f'Attachment not found: {attachment_id}')
    
    attachment = response['TransitGatewayVpcAttachments'][0]
    logger.info(f'VPC: {attachment["VpcId"]}, State: {attachment["State"]}')
    
    return attachment

def check_existing_attachment(vpc_id, tgw_id):
    """既存のAttachmentがないか確認"""
    logger.info(f'既存Attachment確認: VPC={vpc_id}, TGW={tgw_id}')
    
    filters = [
        {'Name': 'vpc-id', 'Values': [vpc_id]},
        {'Name': 'transit-gateway-id', 'Values': [tgw_id]},
        {'Name': 'state', 'Values': ['available', 'pending']}
    ]
    
    response = client.describe_transit_gateway_vpc_attachments(
        Filters=filters
    )
    
    attachments = response['TransitGatewayVpcAttachments']
    
    if attachments:
        existing = attachments[0]
        logger.info(f'既存Attachment発見: {existing["TransitGatewayAttachmentId"]}, State: {existing["State"]}')
        return existing
    
    logger.info('既存Attachmentなし')
    return None

# ==================== 削除処理 ====================

def check_attachment_state(attachment_id):
    """Attachmentが削除可能な状態か確認"""
    attachment = get_attachment_info(attachment_id)
    state = attachment['State']
    
    if state in ['deleting', 'deleted']:
        logger.info(f'既に削除済みまたは削除中: {state}')
        return False, attachment
    
    if state != 'available':
        logger.warning(f'想定外の状態: {state}')
    
    return True, attachment

def delete_attachment(attachment_id):
    """Transit Gateway Attachmentを削除"""
    logger.info(f'Attachment削除開始: {attachment_id}')
    
    response = client.delete_transit_gateway_vpc_attachment(
        TransitGatewayAttachmentId=attachment_id
    )
    
    deleted_attachment = response['TransitGatewayVpcAttachment']
    logger.info(f'削除要求完了: State={deleted_attachment["State"]}')
    
    return deleted_attachment

def handle_remove():
    """削除処理のハンドラ"""
    logger.info('■ Transit Gateway Attachment 削除開始')
    
    if not TGW_ATTACHMENT_ID:
        raise Exception('環境変数 TGW_ATTACHMENT_ID が設定されていません')
    
    # 削除前の情報を記録
    can_delete, attachment_info = check_attachment_state(TGW_ATTACHMENT_ID)
    
    if not can_delete:
        return {
            'statusCode': 200,
            'body': json.dumps({
                'action': 'remove',
                'message': 'Attachment is already deleted or deleting',
                'attachmentId': TGW_ATTACHMENT_ID,
                'state': attachment_info.get('State', 'unknown')
            })
        }
    
    # 削除実行
    result = delete_attachment(TGW_ATTACHMENT_ID)
    
    logger.info('■ 削除完了')
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'action': 'remove',
            'message': 'Transit Gateway Attachment deletion initiated',
            'attachmentId': TGW_ATTACHMENT_ID,
            'vpcId': attachment_info['VpcId'],
            'transitGatewayId': attachment_info['TransitGatewayId'],
            'previousState': attachment_info['State'],
            'newState': result['State'],
            'estimatedMonthlySavings': '$47'
        })
    }

# ==================== 作成処理 ====================

def create_attachment(tgw_id, vpc_id, subnet_ids, tag_name):
    """Transit Gateway Attachmentを作成"""
    logger.info(f'Attachment作成開始: TGW={tgw_id}, VPC={vpc_id}')
    logger.info(f'Subnets: {subnet_ids}')
    
    response = client.create_transit_gateway_vpc_attachment(
        TransitGatewayId=tgw_id,
        VpcId=vpc_id,
        SubnetIds=subnet_ids,
        TagSpecifications=[
            {
                'ResourceType': 'transit-gateway-attachment',
                'Tags': [
                    {'Key': 'Name', 'Value': tag_name}
                ]
            }
        ]
    )
    
    attachment = response['TransitGatewayVpcAttachment']
    logger.info(f'作成完了: {attachment["TransitGatewayAttachmentId"]}, State: {attachment["State"]}')
    
    return attachment

def wait_for_attachment(attachment_id, max_wait=180):
    """Attachmentがavailable状態になるまで待機（最大3分）"""
    logger.info(f'Attachment状態確認: {attachment_id}')
    
    elapsed = 0
    interval = 10
    
    while elapsed < max_wait:
        response = client.describe_transit_gateway_vpc_attachments(
            TransitGatewayAttachmentIds=[attachment_id]
        )
        
        if not response['TransitGatewayVpcAttachments']:
            raise Exception(f'Attachment not found: {attachment_id}')
        
        state = response['TransitGatewayVpcAttachments'][0]['State']
        logger.info(f'State: {state} (経過: {elapsed}秒)')
        
        if state == 'available':
            logger.info('Attachment準備完了')
            return True
        
        if state in ['failed', 'deleted', 'deleting']:
            raise Exception(f'Attachment creation failed: {state}')
        
        time.sleep(interval)
        elapsed += interval
    
    logger.warning(f'タイムアウト: {max_wait}秒経過')
    return False

def handle_add():
    """作成処理のハンドラ"""
    logger.info('■ Transit Gateway Attachment 作成開始')
    
    if not all([TGW_ID, VPC_ID, SUBNET_IDS]):
        raise Exception('環境変数 TGW_ID, VPC_ID, SUBNET_IDS が必要です')
    
    # サブネットIDをリストに変換
    subnet_ids = [s.strip() for s in SUBNET_IDS.split(',')]
    
    # 既存Attachment確認
    existing = check_existing_attachment(VPC_ID, TGW_ID)
    if existing:
        return {
            'statusCode': 200,
            'body': json.dumps({
                'action': 'add',
                'message': 'Attachment already exists',
                'attachmentId': existing['TransitGatewayAttachmentId'],
                'state': existing['State'],
                'vpcId': VPC_ID,
                'transitGatewayId': TGW_ID
            })
        }
    
    # 作成実行
    attachment = create_attachment(TGW_ID, VPC_ID, subnet_ids, TAG_NAME)
    attachment_id = attachment['TransitGatewayAttachmentId']
    
    # 状態確認（タイムアウトしても継続）
    is_ready = wait_for_attachment(attachment_id)
    
    logger.info('■ 作成完了')
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'action': 'add',
            'message': 'Transit Gateway Attachment created',
            'attachmentId': attachment_id,
            'vpcId': VPC_ID,
            'transitGatewayId': TGW_ID,
            'subnetIds': subnet_ids,
            'state': attachment['State'],
            'isReady': is_ready,
            'estimatedMonthlyCost': '$47',
            'tagName': TAG_NAME
        })
    }

# ==================== メインハンドラ ====================

def lambda_handler(event, context):
    """Lambda エントリーポイント"""
    
    try:
        # アクションを取得（デフォルト: remove）
        action = event.get('action', 'remove').lower()
        
        logger.info(f'=== Action: {action} ===')
        
        if action == 'remove':
            return handle_remove()
        elif action == 'add':
            return handle_add()
        else:
            raise Exception(f'Invalid action: {action}. Use "add" or "remove"')
            
    except Exception as e:
        logger.error(f'エラー: {str(e)}')
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'event': event
            })
        }
