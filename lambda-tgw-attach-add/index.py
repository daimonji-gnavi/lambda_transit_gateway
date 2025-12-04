import os
import boto3
import logging
import json

"""
Transit Gateway Attachment 作成用 Lambda関数
用途: プロジェクト再開時のネットワーク復旧
"""

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 環境変数から設定を取得
TGW_ID = os.environ['TGW_ID']
VPC_ID = os.environ['VPC_ID']
SUBNET_IDS = os.environ['SUBNET_IDS']  # カンマ区切り
TAG_NAME = os.environ.get('TAG_NAME', 'v2-tgwa-test-magent')

client = boto3.client('ec2')

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
    
    import time
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

def lambda_handler(event, context):
    """Lambda エントリーポイント"""
    logger.info('■ Transit Gateway Attachment 作成開始')
    
    try:
        # サブネットIDをリストに変換
        subnet_ids = [s.strip() for s in SUBNET_IDS.split(',')]
        
        # 既存Attachment確認
        existing = check_existing_attachment(VPC_ID, TGW_ID)
        if existing:
            return {
                'statusCode': 200,
                'body': json.dumps({
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
        
    except Exception as e:
        logger.error(f'エラー: {str(e)}')
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'vpcId': VPC_ID,
                'transitGatewayId': TGW_ID
            })
        }
