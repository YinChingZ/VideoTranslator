import sys
import os
import logging
import argparse
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QCoreApplication

# 添加项目根目录到 Python 路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.gui.main_window import MainWindow
from app.utils.logger import setup_logger
from app.config import get_config_manager
from app.utils.temp_files import TempFileManager
from app.utils.system_health_checker import perform_startup_check, can_start_application

def check_dependencies():
    """全面检查系统依赖是否正确安装"""
    missing_deps = []
    failed_checks = []
    
    # 检查Python版本
    import sys
    if sys.version_info < (3, 8):
        failed_checks.append(f"Python版本过低 ({sys.version}), 需要3.8+")
    
    # 检查关键Python包
    required_packages = {
        'PyQt5': 'PyQt5',
        'ffmpeg-python': 'ffmpeg',
        'whisper': 'openai-whisper',
        'requests': 'requests',
        'numpy': 'numpy',
        'sqlite3': None  # 内置模块
    }
    
    for package, pip_name in required_packages.items():
        try:
            __import__(package)
        except ImportError:
            if pip_name:
                missing_deps.append(f"{package} (安装: pip install {pip_name})")
            else:
                failed_checks.append(f"内置模块 {package} 不可用")
    
    # 检查FFmpeg可执行文件
    import subprocess
    ffmpeg_commands = ['ffmpeg', 'ffprobe']
    for cmd in ffmpeg_commands:
        try:
            subprocess.check_output([cmd, '-version'], 
                                   stderr=subprocess.STDOUT, 
                                   timeout=5)
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            failed_checks.append(f"{cmd} 不可用 (请安装FFmpeg并添加到PATH)")
    
    # 检查磁盘空间 (至少1GB)
    import shutil
    try:
        free_space = shutil.disk_usage('.').free / (1024**3)  # GB
        if free_space < 1:
            failed_checks.append(f"磁盘空间不足 ({free_space:.1f}GB), 建议至少1GB")
    except Exception:
        pass
    
    # 检查网络连接（可选）
    try:
        import urllib.request
        urllib.request.urlopen('https://www.google.com', timeout=3)
    except Exception:
        # 网络问题不是致命错误，只记录警告
        logging.warning("网络连接检查失败，某些功能可能受限")
    
    # 汇总检查结果
    if missing_deps or failed_checks:
        error_msg = "系统依赖检查失败:\n"
        if missing_deps:
            error_msg += "\n缺少Python包:\n" + "\n".join(f"  - {dep}" for dep in missing_deps)
        if failed_checks:
            error_msg += "\n系统环境问题:\n" + "\n".join(f"  - {check}" for check in failed_checks)
        
        logging.error(error_msg)
        return False, error_msg
    
    return True, "所有依赖检查通过"

def parse_arguments():
    """处理命令行参数"""
    parser = argparse.ArgumentParser(description='视频翻译处理系统')
    parser.add_argument('file', nargs='?', help='要打开的视频文件路径')
    parser.add_argument('--debug', action='store_true', help='启用调试模式')
    return parser.parse_args()

def handle_exception(exc_type, exc_value, exc_traceback):
    """全局异常处理函数"""
    if issubclass(exc_type, KeyboardInterrupt):
        # 正常退出，不记录堆栈跟踪
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    # 记录详细异常信息到日志文件
    logging.error("未捕获的异常:", exc_info=(exc_type, exc_value, exc_traceback))
    
    # 对于GUI应用，可以在这里添加用户友好的错误提示
    try:
        from PyQt5.QtWidgets import QMessageBox
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setText("程序发生意外错误")
        msg.setInformativeText(str(exc_value))
        msg.setWindowTitle("错误")
        msg.setDetailedText(f"类型: {exc_type.__name__}\n"
                          f"详情: {str(exc_value)}\n\n"
                          f"详细信息已记录到日志文件")
        msg.exec()
    except ImportError:
        # 如果在非GUI环境中，只打印错误
        print(f"错误: {exc_type.__name__}: {exc_value}", file=sys.stderr)
    except Exception:
        # 如果在显示错误对话框时出错，则回退到标准错误输出
        print(f"严重错误: {exc_type.__name__}: {exc_value}", file=sys.stderr)

def main():
    # 解析命令行参数
    args = parse_arguments()
    
    # 设置日志系统
    log_level = logging.DEBUG if args.debug else logging.INFO
    setup_logger(log_level)
    
    # 设置全局异常处理器
    sys.excepthook = handle_exception
    
    # 创建临时文件管理器
    temp_manager = TempFileManager()
    
    # 设置高DPI支持，须在创建 QApplication 之前
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    # 创建应用程序实例
    app = QApplication(sys.argv)
    app.setApplicationName("VideoTranslator")
    app.setOrganizationName("VideoTranslator")
    app.setApplicationDisplayName("视频翻译处理系统")
    app.setApplicationVersion(get_config_manager().config.app_version)
    
    # 加载配置
    config_manager = get_config_manager()
    config = config_manager.config
    
    # 执行系统健康检查
    logging.info("执行系统健康检查...")
    health_report = perform_startup_check()
    
    # 检查是否可以启动应用
    if not can_start_application(health_report):
        from PyQt5.QtWidgets import QMessageBox
        
        # 创建详细错误对话框
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle("系统环境检查失败")
        msg_box.setText(health_report['status_message'])
        msg_box.setInformativeText("请根据下方详细信息解决环境问题后重试。")
        
        # 构建详细错误信息
        details = []
        if health_report['issues']:
            details.append("严重问题:")
            details.extend([f"• {issue}" for issue in health_report['issues']])
        if health_report['warnings']:
            details.append("\n警告:")
            details.extend([f"• {warning}" for warning in health_report['warnings']])
        if health_report['recommendations']:
            details.append("\n建议:")
            details.extend(health_report['recommendations'])
        
        msg_box.setDetailedText('\n'.join(details))
        msg_box.exec()
        return 1
    
    # 显示健康检查结果（如果有警告）
    if health_report['warnings_count'] > 0:
        from PyQt5.QtWidgets import QMessageBox
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle("系统环境警告")
        msg_box.setText(f"发现 {health_report['warnings_count']} 个警告，应用可以启动但可能影响部分功能。")
        msg_box.setInformativeText("建议查看详细信息并考虑解决这些问题。")
        
        warning_details = "\n".join([f"• {warning}" for warning in health_report['warnings']])
        if health_report['recommendations']:
            warning_details += "\n\n建议:\n" + "\n".join(health_report['recommendations'])
        
        msg_box.setDetailedText(warning_details)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Ignore)
        msg_box.setDefaultButton(QMessageBox.StandardButton.Ok)
        
        result = msg_box.exec()
        if result == QMessageBox.StandardButton.Ignore:
            logging.info("用户选择忽略系统警告，继续启动应用")
    
    logging.info(f"系统健康检查完成: {health_report['status_message']}")
    
    # 创建并显示主窗口
    window = MainWindow(config, temp_manager)
    window.show()
    
    # 如果提供了文件参数，直接打开该文件
    if args.file and os.path.exists(args.file):
        window.open_video(args.file)
    else:
        # 没有文件参数时，显示欢迎信息
        logging.info("应用程序启动，等待用户操作")
        window.status_label.setText("就绪，请打开或导入视频文件")
    
    # 执行应用程序
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
