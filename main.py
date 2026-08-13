import argparse
import logging
import os
import sys

from PyQt5.QtCore import QCoreApplication, Qt
from PyQt5.QtWidgets import QApplication

# 添加项目根目录到 Python 路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.config import get_config_manager
from app.gui.main_window import MainWindow
from app.utils.logger import setup_logger
from app.utils.system_health_checker import can_start_application, perform_startup_check
from app.utils.temp_files import TempFileManager


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
    
    logging.info(f"系统健康检查完成: {health_report['status_message']}")
    
    # 创建并显示主窗口
    window = MainWindow(config, temp_manager)
    if health_report['warnings_count'] > 0:
        report_path = health_report.get("report_path")
        window.status_label.setText(
            f"就绪 · {health_report['warnings_count']} 项可选能力受限"
        )
        tooltip = "\n".join(health_report["warnings"])
        if report_path:
            tooltip += f"\n\n完整报告：{report_path}"
        window.status_label.setToolTip(tooltip)
    window.show()
    
    # 如果提供了文件参数，直接打开该文件
    if args.file and os.path.exists(args.file):
        window.open_video(args.file)
    elif health_report['warnings_count'] == 0:
        # 没有文件参数时，显示欢迎信息
        logging.info("应用程序启动，等待用户操作")
        window.status_label.setText("就绪，请打开或导入视频文件")
    
    # 执行应用程序
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
