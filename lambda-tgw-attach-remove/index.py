import os
import boto3
import logging
import json
import time

"""
Transit Gateway Attachment 削除用 Lambda関数
用途: プロジェクト凍結時のコスト削減（$47/月 → $0）
"""

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 環境変数から設定を取得
TGW_ATTACHMENT_ID = os.environ['TGW_ATTACHMENT_ID']

client = boto3.client('ec2')

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

def check_attachment_state(attachment_id):
    """Attachmentが削除可能な状態か確認"""
    attachment = get_attachment_info(attachment_id)
    state = attachment['State']
    
    if state in ['deleting', 'deleted']:
        logger.info(f'既に削除済みまたは削除中: {state}')
        return False
    
    if state != 'available':
        logger.warning(f'想定外の状態: {state}')
    
    return True

def delete_attachment(attachment_id):
    """Transit Gateway Attachmentを削除"""
    logger.info(f'Attachment削除開始: {attachment_id}')
    
    response = client.delete_transit_gateway_vpc_attachment(
        TransitGatewayAttachmentId=attachment_id
    )
    
    deleted_attachment = response['TransitGatewayVpcAttachment']
    logger.info(f'削除要求完了: State={deleted_attachment["State"]}')
    
    return deleted_attachment

def lambda_handler(event, context):
    """Lambda エントリーポイント"""
    logger.info('■ Transit Gateway Attachment 削除開始')
    
    try:
        # 削除前の情報を記録
        attachment_info = get_attachment_info(TGW_ATTACHMENT_ID)
        
        # 状態確認
        if not check_attachment_state(TGW_ATTACHMENT_ID):
            return {
                'statusCode': 200,
                'body': json.dumps({
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
                'message': 'Transit Gateway Attachment deletion initiated',
                'attachmentId': TGW_ATTACHMENT_ID,
                'vpcId': attachment_info['VpcId'],
                'transitGatewayId': attachment_info['TransitGatewayId'],
                'previousState': attachment_info['State'],
                'newState': result['State'],
                'estimatedMonthlySavings': '$47'
            })
        }
        
    except Exception as e:
        logger.error(f'エラー: {str(e)}')
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'attachmentId': TGW_ATTACHMENT_ID
            })
        }
