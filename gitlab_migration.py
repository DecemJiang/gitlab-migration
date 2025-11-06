#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GitLab 群组和项目迁移脚本

功能：将源GitLab实例中的群组和项目按照1:1的路径迁移到目标GitLab实例
用法：python gitlab_migration.py --source-url <源GitLab URL> --source-token <源访问令牌> \
                               --target-url <目标GitLab URL> --target-token <目标访问令牌> \
                               --source-group <源群组路径>
"""

import argparse
import os
import sys
import time
import logging
import concurrent.futures
from typing import Dict, List, Tuple, Optional

# 设置日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
            logging.FileHandler("gitlab_migration.log", encoding='utf-8'),
            logging.StreamHandler()
        ]
)
logger = logging.getLogger(__name__)

# 尝试导入gitlab库，如果没有安装则提示用户
try:
    import gitlab
except ImportError:
    logger.error("请先安装python-gitlab库：pip install python-gitlab")
    sys.exit(1)


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='GitLab 群组和项目迁移脚本')
    parser.add_argument('--source-url', required=True, help='源GitLab实例的URL')
    parser.add_argument('--source-token', required=True, help='源GitLab实例的访问令牌')
    parser.add_argument('--target-url', required=True, help='目标GitLab实例的URL')
    parser.add_argument('--target-token', required=True, help='目标GitLab实例的访问令牌')
    parser.add_argument('--source-group', required=True, help='源群组的路径（例如：group/subgroup）')
    parser.add_argument('--timeout', type=int, default=30, help='API请求超时时间（秒）')
    parser.add_argument('--verify-ssl', type=bool, default=True, help='是否验证SSL证书')
    parser.add_argument('--max-workers', type=int, default=5, help='并发迁移的最大工作线程数')
    parser.add_argument('--overwrite', action='store_true', help='是否覆盖已存在的项目（默认不覆盖）')
    return parser.parse_args()


def connect_to_gitlab(url: str, token: str, timeout: int, verify_ssl: bool):
    """连接到GitLab实例"""
    try:
        # 添加keep_base_url=True参数以避免URL不匹配警告和可能的认证问题
        gl = gitlab.Gitlab(url, private_token=token, timeout=timeout, ssl_verify=verify_ssl, keep_base_url=True)
        gl.auth()  # 验证连接和令牌
        logger.info(f"成功连接到GitLab实例: {url}")
        return gl
    except gitlab.exceptions.GitlabAuthenticationError:
        logger.error(f"连接到GitLab实例 {url} 失败：认证错误，请检查访问令牌")
        sys.exit(1)
    except Exception as e:
        logger.error(f"连接到GitLab实例 {url} 失败: {str(e)}")
        sys.exit(1)


def get_source_group(source_gl, group_path: str):
    """获取源群组对象"""
    try:
        group = source_gl.groups.get(group_path)
        logger.info(f"成功获取源群组: {group.name} (ID: {group.id})")
        return group
    except gitlab.exceptions.GitlabGetError:
        logger.error(f"无法找到源群组: {group_path}")
        sys.exit(1)


def create_target_group_structure(target_gl, group_path: str, source_group):
    """
    创建目标群组结构
    处理嵌套群组的情况，确保所有父群组都存在
    """
    # 分割群组路径，获取各级群组名称
    path_parts = group_path.split('/')
    current_path = ""
    parent_group = None
    
    # 逐级创建或获取群组
    for i, part in enumerate(path_parts):
        if current_path:
            current_path += f"/{part}"
        else:
            current_path = part
        
        try:
            # 尝试获取群组
            group = target_gl.groups.get(current_path)
            logger.info(f"使用现有目标群组: {current_path}")
        except gitlab.exceptions.GitlabGetError:
            # 创建新群组
            group_data = {
                'name': part,
                'path': part,
                'visibility': source_group.visibility,
            }
            
            if i == 0:  # 顶级群组
                group = target_gl.groups.create(group_data)
            else:  # 子群组
                group_data['parent_id'] = parent_group.id
                group = target_gl.groups.create(group_data)
            
            logger.info(f"创建目标群组: {current_path}")
        
        parent_group = group
    
    return parent_group


def migrate_project(source_gl, target_gl, 
                   project, target_group, overwrite=False):
    """迁移单个项目"""
    # 为每个线程创建独立的GitLab连接，避免并发问题
    source_url = source_gl.url
    source_token = source_gl.private_token
    target_url = target_gl.url
    target_token = target_gl.private_token
    timeout = source_gl.timeout
    verify_ssl = source_gl.ssl_verify
    
    # 创建线程本地的GitLab连接
    thread_source_gl = gitlab.Gitlab(source_url, private_token=source_token, 
                                   timeout=timeout, ssl_verify=verify_ssl, keep_base_url=True)
    thread_target_gl = gitlab.Gitlab(target_url, private_token=target_token, 
                                   timeout=timeout, ssl_verify=verify_ssl, keep_base_url=True)
    
    logger.info(f"开始迁移项目: {project.name} (ID: {project.id})")
    
    try:
        # 第一步：先只使用项目名称进行初步检查，避免不必要的API调用
        project_name = project.name
        target_group_path = target_group.full_path
        
        # 检查项目是否已存在（使用名称进行初步检查）
        try:
            existing_project = thread_target_gl.projects.get(f"{target_group_path}/{project_name}")
            if overwrite:
                logger.warning(f"项目 {project_name} 已存在，正在删除以实现覆盖")
                existing_project.delete()
                # 删除后需要等待一小段时间，确保GitLab完全处理完删除操作
                time.sleep(3)
                logger.info(f"已删除现有项目，准备重新导入: {project_name}")
            else:
                logger.info(f"项目 {project_name} 已存在且未启用覆盖模式，跳过迁移")
                return None
        except gitlab.exceptions.GitlabGetError:
            # 项目不存在，继续迁移
            logger.info(f"项目 {project_name} 在目标GitLab中不存在，开始迁移")
        except Exception as e:
            if overwrite:
                logger.error(f"删除已存在项目时出错: {str(e)}")
                # 继续尝试导入，可能会失败但至少尝试了
                logger.info(f"继续尝试导入项目: {project_name}")
            else:
                logger.error(f"检查项目是否存在时出错: {str(e)}")
                return None
        
        # 只有在确定需要导入时，才获取完整项目对象和执行后续操作
        logger.info(f"准备获取完整项目信息: {project_name}")
        thread_project = thread_source_gl.projects.get(project.id)
        target_path = thread_project.path
        target_name = thread_project.name
        
        # 再次检查（使用准确的path，避免名称和路径不一致的情况）
        if target_path != project_name:
            try:
                existing_project = thread_target_gl.projects.get(f"{target_group_path}/{target_path}")
                if overwrite:
                    logger.warning(f"项目路径 {target_path} 已存在，正在删除以实现覆盖")
                    existing_project.delete()
                    time.sleep(3)
                else:
                    logger.info(f"项目路径 {target_path} 已存在且未启用覆盖模式，跳过迁移")
                    return None
            except gitlab.exceptions.GitlabGetError:
                pass
            except Exception as e:
                logger.error(f"使用path检查项目是否存在时出错: {str(e)}")
                return None
        
        # 项目不存在或已删除，继续导出和导入
        # 导出项目
        export = thread_project.exports.create()
        export.refresh()
        
        # 等待导出完成
        while export.export_status != 'finished':
            time.sleep(5)
            export.refresh()
            if export.export_status == 'failed':
                logger.error(f"项目导出失败: {thread_project.name}")
                return None
        
        # 下载导出文件
        export_file = export.download()
        
        # 检查导出文件大小，添加警告
        file_size_mb = len(export_file) / (1024 * 1024)
        logger.info(f"项目 {thread_project.name} 导出文件大小: {file_size_mb:.2f} MB")
        
        # 如果文件较大，添加警告信息
        if file_size_mb > 100:
            logger.warning(f"项目文件较大 ({file_size_mb:.2f} MB)，可能会遇到上传限制问题")
        
        # 增加超时时间以处理大文件
        original_timeout = thread_target_gl.timeout
        if file_size_mb > 200:
            # 对于大文件，增加超时时间
            thread_target_gl.timeout = max(original_timeout, 120)
            logger.info(f"为大文件导入增加超时时间至 {thread_target_gl.timeout} 秒")
        
        try:
            # 在目标群组中导入项目
            import_project = thread_target_gl.projects.import_project(
                file=export_file,
                path=target_path,
                namespace=target_group.id,
                name=target_name
            )
        except Exception as e:
            # 恢复原始超时设置
            thread_target_gl.timeout = original_timeout
            
            # 检查是否是413错误
            if '413: Request Entity Too Large' in str(e):
                logger.error(f"项目 {thread_project.name} 太大 ({file_size_mb:.2f} MB)，超过目标GitLab服务器上传限制")
                logger.info("建议：")
                logger.info("1. 增加GitLab服务器的client_max_body_size配置")
                logger.info("2. 或尝试分阶段迁移：先迁移代码，再手动迁移大文件")
            raise
        finally:
            # 恢复原始超时设置
            thread_target_gl.timeout = original_timeout
        
        # 等待导入完成
        # 检查返回值类型，有些版本可能返回字典而不是对象
        if isinstance(import_project, dict):
            # 如果是字典，获取项目ID
            project_id = import_project.get('id')
            if not project_id:
                logger.error(f"项目导入失败，无法获取项目ID: {project.name}")
                return None
            
            # 获取完整的项目对象
            import_project = target_gl.projects.get(project_id)
        
        # 等待导入完成
        while hasattr(import_project, 'import_status') and import_project.import_status != 'finished':
            time.sleep(5)
            import_project.refresh()
            if hasattr(import_project, 'import_status') and import_project.import_status == 'failed':
                logger.error(f"项目导入失败: {project.name}")
                return None
        
        logger.info(f"项目迁移成功: {thread_project.name} -> {target_group.full_path}/{target_path}")
        return import_project
    
    except Exception as e:
        logger.error(f"迁移项目 {thread_project.name} 时出错: {str(e)}")
        return None


def migrate_group(source_gl: gitlab.Gitlab, target_gl: gitlab.Gitlab, 
                 source_group_path: str, max_workers: int = 5, overwrite: bool = False) -> None:
    """迁移整个群组（包括子群组和项目）"""
    # 获取源群组
    source_group = get_source_group(source_gl, source_group_path)
    
    # 创建目标群组结构
    target_group = create_target_group_structure(target_gl, source_group_path, source_group)
    
    # 迁移当前群组中的项目
    projects = source_group.projects.list(all=True)
    logger.info(f"在群组 {source_group_path} 中发现 {len(projects)} 个项目")
    
    success_count = 0
    failed_count = 0
    
    # 使用线程池并发迁移项目
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有迁移任务
        future_to_project = {executor.submit(migrate_project, source_gl, target_gl, project, target_group, overwrite): project for project in projects}
        
        # 收集结果
        for future in concurrent.futures.as_completed(future_to_project):
            project = future_to_project[future]
            try:
                result = future.result()
                if result:
                    success_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logger.error(f"处理项目 {project.name} 时发生异常: {str(e)}")
                failed_count += 1
    
    # 递归处理子群组
    subgroups = source_group.subgroups.list(all=True)
    logger.info(f"在群组 {source_group_path} 中发现 {len(subgroups)} 个子群组")
    
    for subgroup in subgroups:
        subgroup_path = f"{source_group_path}/{subgroup.path}"
        logger.info(f"开始迁移子群组: {subgroup_path}")
        migrate_group(source_gl, target_gl, subgroup_path, max_workers=max_workers, overwrite=overwrite)
    
    logger.info(f"群组 {source_group_path} 迁移完成 - 成功: {success_count}, 失败: {failed_count}")


def main():
    """主函数"""
    start_time = time.time()
    logger.info("=== GitLab 迁移任务开始 ===")
    
    try:
        # 解析参数
        args = parse_arguments()
        
        # 连接到源GitLab和目标GitLab
        source_gl = connect_to_gitlab(args.source_url, args.source_token, args.timeout, args.verify_ssl)
        target_gl = connect_to_gitlab(args.target_url, args.target_token, args.timeout, args.verify_ssl)
        
        # 执行迁移
        migrate_group(source_gl, target_gl, args.source_group, max_workers=args.max_workers, overwrite=args.overwrite)
        
        end_time = time.time()
        logger.info(f"=== GitLab 迁移任务完成，耗时: {(end_time - start_time):.2f} 秒 ===")
        
    except KeyboardInterrupt:
        logger.info("迁移任务被用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"迁移过程中发生错误: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()