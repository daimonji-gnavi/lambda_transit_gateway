# Transit Gateway Attachment ON/OFF Lambda Function

## 概要
プロジェクト凍結時のコスト削減のため、Transit Gateway Attachmentを削除・再作成する統合Lambda関数

## コスト削減効果
- **削除時**: $47/月 → $0
- **再作成時**: $0 → $47/月

## Lambda関数

**ファイル**: `index.py`

### 環境変数

#### 必須（削除用）
```
TGW_ATTACHMENT_ID=tgw-attach-02be575b90d39d0c4
```

#### 必須（作成用）
```
TGW_ID=tgw-00791c5c24815d589
VPC_ID=vpc-0709aa89bfb9f5ab4
SUBNET_IDS=subnet-xxxxxxxx,subnet-yyyyyyyy
```

#### オプション
```
TAG_NAME=v2-tgwa-test-magent
```

### IAMポリシー
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeTransitGatewayVpcAttachments",
        "ec2:DeleteTransitGatewayVpcAttachment",
        "ec2:CreateTransitGatewayVpcAttachment",
        "ec2:CreateTags"
      ],
      "Resource": "*"
    }
  ]
}
```

## デプロイ手順

### 1. Subnet IDsの取得
```bash
aws ec2 describe-transit-gateway-vpc-attachments \
  --profile gnaws-test-magent-GmcpUser \
  --transit-gateway-attachment-ids tgw-attach-02be575b90d39d0c4 \
  --query 'TransitGatewayVpcAttachments[0].SubnetIds' \
  --output text
```

### 2. Lambda関数の作成
```bash
# ZIPファイル作成
zip function.zip index.py

# Lambda関数作成
aws lambda create-function \
  --profile gnaws-test-magent-GmcpUser \
  --function-name transit-gateway-attachment-control \
  --runtime python3.12 \
  --role arn:aws:iam::783764585791:role/lambda-tgw-role \
  --handler index.lambda_handler \
  --zip-file fileb://function.zip \
  --timeout 300 \
  --environment Variables="{
    TGW_ATTACHMENT_ID=tgw-attach-02be575b90d39d0c4,
    TGW_ID=tgw-00791c5c24815d589,
    VPC_ID=vpc-0709aa89bfb9f5ab4,
    SUBNET_IDS=subnet-xxx,subnet-yyy,
    TAG_NAME=v2-tgwa-test-magent
  }"
```

## 実行方法

### 削除（コスト削減）
```bash
aws lambda invoke \
  --profile gnaws-test-magent-GmcpUser \
  --function-name transit-gateway-attachment-control \
  --payload '{"action":"remove"}' \
  /tmp/remove-result.json

cat /tmp/remove-result.json | jq
```

### 作成（プロジェクト再開）
```bash
aws lambda invoke \
  --profile gnaws-test-magent-GmcpUser \
  --function-name transit-gateway-attachment-control \
  --payload '{"action":"add"}' \
  /tmp/add-result.json

cat /tmp/add-result.json | jq
```

## テストイベント例

### 削除テスト
```json
{
  "action": "remove"
}
```

### 作成テスト
```json
{
  "action": "add"
}
```

## 注意事項

1. **削除時**
   - 他システムとのネットワーク接続が切断される
   - VPC内のリソースはインターネットアクセス不可になる可能性
   
2. **再作成時**
   - Attachmentが`available`状態になるまで数分かかる
   - Transit Gatewayの所有者が別アカウントの場合、承認が必要になる可能性
   
3. **IAMロール**
   - デプロイ前に適切なIAMロールを作成すること
   - 最小権限の原則に従ってポリシーを設定

## 参考
- 元となったNAT Gateway ON/OFF Lambda: `gnaws-prod-moas` アカウント
  - `add-natgateway`
  - `remove-natgateway`
