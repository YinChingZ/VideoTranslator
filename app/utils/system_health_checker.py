#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系统健康检查模块
在应用启动前进行全面的系统检查
"""

import os
import sys
import logging
import platform
import shutil
import socket
import subprocess
import importlib.util
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class SystemHealthChecker:
    """系统健康检查器"""
    
    def __init__(self):
        self.check_results = {}
        self.issues = []
        self.warnings = []
        self.recommendations = []
    
    def run_full_check(self) -> Dict[str, Any]:
        """运行完整的系统检查"""
        logger.info("开始系统健康检查...")
        
        # 执行各项检查
        checks = [
            ("Python环境", self.check_python_environment),
            ("系统资源", self.check_system_resources),
            ("依赖包", self.check_python_packages),
            ("外部工具", self.check_external_tools),
            ("网络连接", self.check_network_connectivity),
            ("文件系统", self.check_file_system),
            ("配置文件", self.check_configuration),
            ("模型文件", self.check_model_files),
        ]
        
        for check_name, check_func in checks:
            try:
                logger.info(f"检查 {check_name}...")
                result = check_func()
                self.check_results[check_name] = result
                
                if not result.get('status', True):
                    self.issues.append(f"{check_name}: {result.get('message', '检查失败')}")
                elif result.get('warnings'):
                    self.warnings.extend(result['warnings'])
                    
            except Exception as e:
                logger.error(f"检查 {check_name} 时发生错误: {e}")
                self.check_results[check_name] = {
                    'status': False,
                    'message': f'检查失败: {str(e)}',
                    'error': str(e)
                }
                self.issues.append(f"{check_name}: 检查失败 - {str(e)}")
        
        # 生成检查报告
        report = self.generate_report()
        logger.info("系统健康检查完成")
        
        return report
    
    def check_python_environment(self) -> Dict[str, Any]:
        """检查Python环境"""
        result = {'status': True, 'details': {}}
        
        # Python版本检查
        python_version = sys.version_info
        result['details']['python_version'] = f"{python_version.major}.{python_version.minor}.{python_version.micro}"
        
        if python_version < (3, 8):
            result['status'] = False
            result['message'] = f"Python版本过低: {result['details']['python_version']}，需要3.8+版本"
            return result
        
        # 平台信息
        result['details']['platform'] = platform.platform()
        result['details']['architecture'] = platform.architecture()[0]
        
        # 虚拟环境检查
        result['details']['virtual_env'] = {
            'in_venv': hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix),
            'prefix': sys.prefix,
            'executable': sys.executable
        }
        
        return result
    
    def check_system_resources(self) -> Dict[str, Any]:
        """检查系统资源"""
        result = {'status': True, 'details': {}, 'warnings': []}
        
        try:
            import psutil
            
            # 内存检查
            memory = psutil.virtual_memory()
            result['details']['memory'] = {
                'total': memory.total,
                'available': memory.available,
                'percent': memory.percent,
                'total_gb': round(memory.total / (1024**3), 2),
                'available_gb': round(memory.available / (1024**3), 2)
            }
            
            if memory.available < 2 * 1024**3:  # 少于2GB可用内存
                result['warnings'].append("可用内存不足2GB，处理大文件时可能遇到问题")
            
            # 磁盘空间检查
            disk_usage = psutil.disk_usage('/')
            result['details']['disk'] = {
                'total': disk_usage.total,
                'used': disk_usage.used,
                'free': disk_usage.free,
                'percent': (disk_usage.used / disk_usage.total) * 100,
                'free_gb': round(disk_usage.free / (1024**3), 2)
            }
            
            if disk_usage.free < 5 * 1024**3:  # 少于5GB空闲空间
                result['warnings'].append("磁盘空间不足5GB，可能影响临时文件存储")
            
            # CPU信息
            result['details']['cpu'] = {
                'count': psutil.cpu_count(),
                'usage': psutil.cpu_percent()
            }
            
        except ImportError:
            result['warnings'].append("psutil包未安装，无法检查系统资源")
        except Exception as e:
            result['warnings'].append(f"检查系统资源时发生错误: {e}")
        
        return result
    
    def check_python_packages(self) -> Dict[str, Any]:
        """检查Python包依赖"""
        result = {'status': True, 'details': {}, 'missing': [], 'warnings': []}
        
        # 必需的包（包名 -> (导入名, 描述)）
        required_packages = {
            'PyQt5': ('PyQt5', 'GUI框架'),
            'numpy': ('numpy', '数值计算'),
            'torch': ('torch', '深度学习框架'),
            'librosa': ('librosa', '音频处理'),
            'pydub': ('pydub', '音频处理'),
            'ffmpeg-python': ('ffmpeg', '音视频处理'),
            'requests': ('requests', 'HTTP客户端'),
            'opencv-python': ('cv2', '计算机视觉'),
        }
        
        # 可选的包
        optional_packages = {
            'psutil': ('psutil', '系统监控'),
            'scipy': ('scipy', '科学计算'),
            'matplotlib': ('matplotlib', '绘图'),
            'pillow': ('PIL', '图像处理')
        }
        
        # 检查必需包
        for package_name, (import_name, description) in required_packages.items():
            try:
                spec = importlib.util.find_spec(import_name)
                if spec is None:
                    result['missing'].append(f"{package_name} ({description})")
                else:
                    try:
                        module = importlib.import_module(import_name)
                        version = getattr(module, '__version__', 'unknown')
                        result['details'][package_name] = {
                            'installed': True,
                            'version': version,
                            'description': description
                        }
                    except:
                        result['details'][package_name] = {
                            'installed': True,
                            'version': 'unknown',
                            'description': description
                        }
            except Exception as e:
                result['missing'].append(f"{package_name} ({description}) - 检查失败: {e}")
        
        # 检查可选包
        for package_name, (import_name, description) in optional_packages.items():
            try:
                spec = importlib.util.find_spec(import_name)
                if spec is None:
                    result['warnings'].append(f"可选包 {package_name} 未安装，{description}功能可能受限")
                else:
                    try:
                        module = importlib.import_module(import_name)
                        version = getattr(module, '__version__', 'unknown')
                        result['details'][package_name] = {
                            'installed': True,
                            'version': version,
                            'description': description
                        }
                    except:
                        result['details'][package_name] = {
                            'installed': True,
                            'version': 'unknown',
                            'description': description
                        }
            except Exception as e:
                result['warnings'].append(f"检查可选包 {package_name} 时发生错误: {e}")
        
        if result['missing']:
            result['status'] = False
            result['message'] = f"缺少必需的包: {', '.join(result['missing'])}"
        
        return result
    
    def check_external_tools(self) -> Dict[str, Any]:
        """检查外部工具"""
        result = {'status': True, 'details': {}, 'missing': []}
        
        # 必需的外部工具
        required_tools = {
            'ffmpeg': 'FFmpeg音视频处理工具',
            'ffprobe': 'FFprobe媒体信息探测工具'
        }
        
        for tool, description in required_tools.items():
            try:
                # 检验工具是否在PATH中
                tool_path = shutil.which(tool)
                if tool_path:
                    # 获取版本信息
                    try:
                        version_cmd = [tool, '-version'] if tool == 'ffmpeg' else [tool, '-version']
                        version_output = subprocess.check_output(
                            version_cmd, 
                            stderr=subprocess.STDOUT,
                            universal_newlines=True,
                            timeout=10
                        )
                        # 提取版本号
                        version_line = version_output.split('\n')[0]
                        result['details'][tool] = {
                            'installed': True,
                            'path': tool_path,
                            'version': version_line,
                            'description': description
                        }
                    except Exception as e:
                        result['details'][tool] = {
                            'installed': True,
                            'path': tool_path,
                            'version': 'unknown',
                            'description': description,
                            'error': str(e)
                        }
                else:
                    result['missing'].append(f"{tool} ({description})")
            except Exception as e:
                result['missing'].append(f"{tool} ({description}) - 检查失败: {e}")
        
        if result['missing']:
            result['status'] = False
            result['message'] = f"缺少必需的外部工具: {', '.join(result['missing'])}"
        
        return result
    
    def check_network_connectivity(self) -> Dict[str, Any]:
        """检查网络连接"""
        result = {'status': True, 'details': {}, 'warnings': []}
        
        # 测试连接
        test_hosts = [
            ('google.com', 80, 'Google'),
            ('api.openai.com', 443, 'OpenAI API'),
            ('translate.googleapis.com', 443, 'Google Translate API'),
            ('github.com', 443, 'GitHub')
        ]
        
        connected_hosts = []
        failed_hosts = []
        
        for host, port, description in test_hosts:
            try:
                sock = socket.create_connection((host, port), timeout=5)
                sock.close()
                connected_hosts.append(description)
                result['details'][host] = {
                    'reachable': True,
                    'description': description
                }
            except Exception as e:
                failed_hosts.append(f"{description} ({host}:{port})")
                result['details'][host] = {
                    'reachable': False,
                    'description': description,
                    'error': str(e)
                }
        
        if failed_hosts:
            result['warnings'].append(f"无法连接到: {', '.join(failed_hosts)}")
            result['warnings'].append("网络连接问题可能影响翻译服务和模型下载")
        
        result['details']['summary'] = {
            'connected': len(connected_hosts),
            'failed': len(failed_hosts),
            'total': len(test_hosts)
        }
        
        return result
    
    def check_file_system(self) -> Dict[str, Any]:
        """检查文件系统"""
        result = {'status': True, 'details': {}, 'warnings': []}
        
        # 检查重要目录
        important_dirs = [
            ('temp', '临时文件目录'),
            ('models', '模型文件目录'),
            ('logs', '日志文件目录')
        ]
        
        for dir_name, description in important_dirs:
            try:
                # 获取项目根目录
                project_root = Path(__file__).parents[2]
                dir_path = project_root / dir_name
                
                # 检查目录是否存在，不存在则创建
                if not dir_path.exists():
                    dir_path.mkdir(parents=True, exist_ok=True)
                    result['warnings'].append(f"创建了缺失的目录: {dir_path}")
                
                # 检查写权限
                test_file = dir_path / '.write_test'
                try:
                    test_file.write_text('test')
                    test_file.unlink()
                    result['details'][dir_name] = {
                        'exists': True,
                        'writable': True,
                        'path': str(dir_path),
                        'description': description
                    }
                except Exception as e:
                    result['details'][dir_name] = {
                        'exists': True,
                        'writable': False,
                        'path': str(dir_path),
                        'description': description,
                        'error': str(e)
                    }
                    result['warnings'].append(f"目录 {dir_path} 无写权限")
                    
            except Exception as e:
                result['details'][dir_name] = {
                    'exists': False,
                    'writable': False,
                    'description': description,
                    'error': str(e)
                }
                result['warnings'].append(f"检查目录 {dir_name} 时发生错误: {e}")
        
        return result
    
    def check_configuration(self) -> Dict[str, Any]:
        """检查配置文件"""
        result = {'status': True, 'details': {}, 'warnings': []}
        
        try:
            from app.config import get_config_manager
            config_manager = get_config_manager()
            config_loaded = config_manager.load_config()
            config = config_manager.config
            
            result['details']['config_loaded'] = config_loaded
            result['details']['config_path'] = str(config_manager.config_file)
            
            # 检查关键配置项
            key_configs = [
                ('whisper_model', 'Whisper模型'),
                ('translation_provider', '翻译服务提供商'),
                ('supported_video_formats', '支持的视频格式'),
                ('temp_dir', '临时文件目录')
            ]
            
            missing_configs = []
            for key, description in key_configs:
                if not hasattr(config, key):
                    missing_configs.append(f"{key} ({description})")
                else:
                    value = getattr(config, key)
                    result['details'][key] = {
                        'configured': True,
                        'value': str(value) if not isinstance(value, (str, int, float, bool)) else value,
                        'description': description
                    }
            
            if missing_configs:
                result['warnings'].append(f"配置文件中缺少: {', '.join(missing_configs)}")
            
        except Exception as e:
            result['status'] = False
            result['message'] = f"配置文件检查失败: {str(e)}"
            result['details']['error'] = str(e)
        
        return result
    
    def check_model_files(self) -> Dict[str, Any]:
        """检查模型文件"""
        result = {'status': True, 'details': {}, 'warnings': []}
        
        # 检查Whisper模型目录
        try:
            project_root = Path(__file__).parents[2]
            whisper_models_dir = project_root / "model" / "whisper" / "models"
            
            result['details']['whisper_models_dir'] = {
                'exists': whisper_models_dir.exists(),
                'path': str(whisper_models_dir)
            }
            
            if whisper_models_dir.exists():
                # 检查可用的模型文件
                model_files = list(whisper_models_dir.glob("*.pt"))
                result['details']['available_models'] = [f.stem for f in model_files]
                
                if not model_files:
                    result['warnings'].append("未找到Whisper模型文件，首次使用时将自动下载")
                else:
                    result['details']['model_count'] = len(model_files)
            else:
                result['warnings'].append("Whisper模型目录不存在，首次使用时将自动创建")
        
        except Exception as e:
            result['warnings'].append(f"检查模型文件时发生错误: {e}")
        
        return result
    
    def generate_report(self) -> Dict[str, Any]:
        """生成检查报告"""
        # 计算总体状态
        failed_checks = len(self.issues)
        total_checks = len(self.check_results)
        success_rate = ((total_checks - failed_checks) / total_checks) * 100 if total_checks > 0 else 0
        
        # 确定系统状态
        if failed_checks == 0:
            if len(self.warnings) == 0:
                system_status = "excellent"
                status_message = "系统状态优秀，所有检查都通过"
            else:
                system_status = "good"
                status_message = f"系统状态良好，有 {len(self.warnings)} 个警告"
        elif failed_checks <= 2:
            system_status = "warning"
            status_message = f"系统状态需要注意，有 {failed_checks} 个严重问题"
        else:
            system_status = "critical"
            status_message = f"系统状态严重，有 {failed_checks} 个严重问题"
        
        # 生成建议
        if self.issues:
            self.recommendations.append("请解决以下严重问题后再启动应用:")
            self.recommendations.extend([f"• {issue}" for issue in self.issues])
        
        if self.warnings:
            self.recommendations.append("建议解决以下警告以获得更好的体验:")
            self.recommendations.extend([f"• {warning}" for warning in self.warnings])
        
        return {
            'system_status': system_status,
            'status_message': status_message,
            'success_rate': round(success_rate, 1),
            'total_checks': total_checks,
            'failed_checks': failed_checks,
            'warnings_count': len(self.warnings),
            'issues': self.issues,
            'warnings': self.warnings,
            'recommendations': self.recommendations,
            'detailed_results': self.check_results,
            'timestamp': __import__('time').time()
        }
    
    def save_report(self, report: Dict[str, Any], filename: str = None) -> str:
        """保存检查报告到文件"""
        if filename is None:
            timestamp = __import__('time').strftime('%Y%m%d_%H%M%S')
            filename = f"system_health_check_{timestamp}.json"
        
        try:
            project_root = Path(__file__).parents[2]
            logs_dir = project_root / "logs"
            logs_dir.mkdir(exist_ok=True)
            
            report_path = logs_dir / filename
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)
            
            logger.info(f"系统健康检查报告已保存到: {report_path}")
            return str(report_path)
            
        except Exception as e:
            logger.error(f"保存检查报告失败: {e}")
            return ""


def perform_startup_check() -> Dict[str, Any]:
    """执行启动检查"""
    checker = SystemHealthChecker()
    report = checker.run_full_check()
    
    # 保存报告
    checker.save_report(report)
    
    return report


def can_start_application(report: Dict[str, Any]) -> bool:
    """判断是否可以启动应用"""
    return report['system_status'] in ['excellent', 'good', 'warning']


if __name__ == "__main__":
    # 测试系统检查
    logging.basicConfig(level=logging.INFO)
    report = perform_startup_check()
    
    print(f"\n系统健康检查完成!")
    print(f"状态: {report['status_message']}")
    print(f"成功率: {report['success_rate']}%")
    
    if report['issues']:
        print(f"\n严重问题 ({len(report['issues'])}):")
        for issue in report['issues']:
            print(f"  × {issue}")
    
    if report['warnings']:
        print(f"\n警告 ({len(report['warnings'])}):")
        for warning in report['warnings']:
            print(f"  ⚠ {warning}")
    
    if report['recommendations']:
        print(f"\n建议:")
        for rec in report['recommendations']:
            print(f"  {rec}")
    
    can_start = can_start_application(report)
    print(f"\n可以启动应用: {'是' if can_start else '否'}")
