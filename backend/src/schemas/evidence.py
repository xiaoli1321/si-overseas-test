from typing import Any, Literal
from pydantic import BaseModel, Field


class DeviceSnapshot(BaseModel):
    """设备状态快照"""

    sn: str
    type: str | None = None
    device_type: str
    wear_days: float
    wearHours: float | None = None
    device_status: int
    fall_off_status: str
    status: str = "wearing"
    activatedAt: str | None = None
    lastDataAt: str | None = None
    timeZone: str | None = None


class FileMetadata(BaseModel):
    """已绑定文件的元数据快照"""

    file_id: str
    filename: str
    public_url: str
    file_size: int | None = None


class GlucoseVisionAnalysisItem(BaseModel):
    """指尖/连续血糖 VLM 图片识别读数"""

    device_type: Literal["CGM", "BGM"]
    value: float
    unit: str = "mmol/L"
    is_valid: bool = True
    is_reproduced: bool = False


class GlucoseVisionAnalysis(BaseModel):
    """血糖对比图大模型分析快照"""

    glucose_readings: list[GlucoseVisionAnalysisItem]


# ─── 研发诊断证据链 ───


class TimeRange(BaseModel):
    """诊断出异常波动的时段（UTC 时间字符串）"""

    start_at: str
    end_at: str


class JumpPoint(BaseModel):
    """数据跳变点"""

    timestamp: int  # 发生跳变时的 Unix 时间戳（秒）
    pre_value: float  # 跳变前一刻的值 (mmol/L)
    post_value: float  # 跳变后一刻的值 (mmol/L)
    delta: float  # 两次读数变化差绝对值 (mmol/L)


class PersistentlyLowDetails(BaseModel):
    """持续偏低判定数据支撑"""

    max_glucose_24h: float
    actual_low_hours: float
    trigger_segments: list[TimeRange] = Field(default_factory=list)


class NoFluctuationDetails(BaseModel):
    """无波动/平线判定数据支撑"""

    max_glucose_24h: float
    actual_flat_hours: float
    actual_max_delta: float
    trigger_segments: list[TimeRange] = Field(default_factory=list)


class SuddenFluctuationDetails(BaseModel):
    """突变跳点判定数据支撑"""

    jump_count: int
    jump_points: list[JumpPoint] = Field(default_factory=list)


class DataAccuracyDetails(BaseModel):
    """数据准确性诊断特征详情"""

    persistently_low: PersistentlyLowDetails | None = None
    no_fluctuation: NoFluctuationDetails | None = None
    sudden_fluctuation: SuddenFluctuationDetails | None = None


# ─── 主 Evidence 模型 ───


class BaseEvidence(BaseModel):
    """证据链基础类"""

    matched_rules: list[str] = Field(default_factory=list)
    files_metadata: list[FileMetadata] = Field(default_factory=list)


class DataAccuracyEvidence(BaseEvidence):
    """数据准确性 (Data accuracy) 诊断证据"""

    device: DeviceSnapshot
    glucose_series_url: str  # 外置的极简 .json 血糖文件下载 URL 指针
    vision_analysis: GlucoseVisionAnalysis | None = None
    data_accuracy_details: DataAccuracyDetails | None = None


class SensorFallingOffEvidence(BaseEvidence):
    """传感器脱落 (Sensor falling off) 诊断证据"""

    device: DeviceSnapshot


class AlarmSnapshot(BaseModel):
    """报警数据快照"""

    serial_no: str
    latest_alarm_status: int
    latest_sensor_internal_value: int = 0
    abnormal_started_at: str
    abnormal_duration_minutes: int
    raw_device_status: int


class SensorAbnormalEvidence(BaseEvidence):
    """传感器异常 (Sensor Abnormal) 诊断证据"""

    device: DeviceSnapshot
    alarm: AlarmSnapshot


class VisionFeatures(BaseModel):
    """异常特征布尔标签"""

    is_cgm_device_present: bool = False
    is_reproduced_photo: bool = False
    needle_exposed: bool = False
    adhesive_detached: bool = False
    implanter_damage: bool = False


class ApplicationFailureVision(BaseModel):
    """VLM 视觉分析参数"""

    model_name: str
    prompt_version: str
    source: str
    score: float
    features: VisionFeatures
    final_scenario: str | None = None
    final_confidence: float | None = None
    scenarios: list[dict[str, Any]] = Field(default_factory=list)


class ApplicationFailureEvidence(BaseEvidence):
    """贴敷/操作失败 (Application failure) 诊断证据"""

    device: DeviceSnapshot | None = None
    vision: ApplicationFailureVision | None = None
    implantation_scanner: list[dict[str, Any]] = Field(default_factory=list)
    file_ids: list[str] = Field(default_factory=list)
