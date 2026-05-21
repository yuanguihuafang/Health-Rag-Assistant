import { logApi } from "./log";
import { request } from "@/utils/hertz_request";

// 仪表盘统计数据类型定义
export interface DashboardStats {
  totalUsers: number;
  totalNotifications: number;
  totalLogs: number;
  totalKnowledge: number;
  userGrowthRate: number;
  notificationGrowthRate: number;
  logGrowthRate: number;
  knowledgeGrowthRate: number;
}

// 最近活动数据类型
export interface RecentActivity {
  id: number;
  action: string;
  time: string;
  user: string;
  type: "login" | "create" | "update" | "system" | "register" | "alert";
}

// 系统状态数据类型
export interface SystemStatus {
  cpuUsage: number;
  memoryUsage: number;
  diskUsage: number;
  networkStatus: "normal" | "warning" | "error";
}

// 访问趋势数据类型
export interface VisitTrend {
  date: string;
  visits: number;
  users: number;
}

// 仪表盘数据汇总类型
export interface DashboardData {
  stats: DashboardStats;
  recentActivities: RecentActivity[];
  systemStatus: SystemStatus;
  visitTrends: VisitTrend[];
}

// API响应类型
export interface ApiResponse<T> {
  success: boolean;
  code: number;
  message: string;
  data: T;
}

// 仪表盘API接口
export const dashboardApi = {
  // 获取仪表盘统计数据
  getStats: async (): Promise<ApiResponse<DashboardStats>> => {
    return dashboardApi.getRealStats();
  },

  // 获取真实统计数据
  getRealStats: async (): Promise<ApiResponse<DashboardStats>> => {
    try {
      const [userStats, noticeStats, logStats, knowledgeStats] = await Promise.all([
        request
          .get("/api/users/", {
            params: { page: 1, page_size: 1 },
            showError: false,
          })
          .catch(() => ({ success: false, data: { total: 0 } })),
        request
          .get("/api/notice/admin/list/", {
            params: { page: 1, page_size: 1 },
            showError: false,
          })
          .catch(() => ({ success: false, data: { total: 0 } })),
        logApi
          .getList({ page: 1, page_size: 1 })
          .catch(() => ({ success: false, data: { count: 0 } })),
        request
          .get("/api/health-rag/kb/documents/", {
            params: { page: 1, page_size: 1 },
            showError: false,
          })
          .catch(() => ({ success: false, data: { total: 0 } })),
      ]);

      const getTotal = (response: any): number => {
        const data = response?.data || {};
        const pagination = data.pagination || {};
        const candidates = [
          data.total,
          data.count,
          data.total_count,
          pagination.total,
          pagination.count,
          pagination.total_count,
        ];
        for (const value of candidates) {
          const total = Number(value);
          if (Number.isFinite(total)) {
            return total;
          }
        }
        if (Array.isArray(data.list)) return data.list.length;
        if (Array.isArray(data.results)) return data.results.length;
        if (Array.isArray(data.logs)) return data.logs.length;
        if (Array.isArray(data.notices)) return data.notices.length;
        return 0;
      };

      const stats: DashboardStats = {
        totalUsers: getTotal(userStats),
        totalNotifications: getTotal(noticeStats),
        totalLogs: getTotal(logStats),
        totalKnowledge: getTotal(knowledgeStats),
        userGrowthRate: 0,
        notificationGrowthRate: 0,
        logGrowthRate: 0,
        knowledgeGrowthRate: 0,
      };

      return {
        success: true,
        code: 200,
        message: "success",
        data: stats,
      };
    } catch (error) {
      console.error("获取真实统计数据失败:", error);
      return {
        success: false,
        code: 500,
        message: "获取统计数据失败",
        data: {
          totalUsers: 0,
          totalNotifications: 0,
          totalLogs: 0,
          totalKnowledge: 0,
          userGrowthRate: 0,
          notificationGrowthRate: 0,
          logGrowthRate: 0,
          knowledgeGrowthRate: 0,
        },
      };
    }
  },

  // 获取最近活动（从日志接口）
  getRecentActivities: async (
    limit: number = 10,
  ): Promise<ApiResponse<RecentActivity[]>> => {
    try {
      const response = await logApi.getList({ page: 1, page_size: limit });
      if (response.success && response.data) {
        const logs =
          (response.data as any).logs || (response.data as any).results || [];
        const activities: RecentActivity[] = logs.map((log: any) => ({
          id: log.log_id || log.id,
          action:
            log.description ||
            log.operation_description ||
            `${log.action_type_display || log.operation_type} - ${log.module || log.operation_module}`,
          time: formatTimeAgo(log.created_at),
          user: log.username || log.user?.username || "未知用户",
          type: mapLogTypeToActivityType(log.action_type || log.operation_type),
        }));
        return {
          success: true,
          code: 200,
          message: "success",
          data: activities,
        };
      }
      return {
        success: false,
        code: 500,
        message: "获取活动数据失败",
        data: [],
      };
    } catch (error) {
      console.error("获取最近活动失败:", error);
      return {
        success: false,
        code: 500,
        message: "获取活动数据失败",
        data: [],
      };
    }
  },

  // 获取系统状态
  getSystemStatus: async (): Promise<ApiResponse<SystemStatus>> => {
    try {
      const response: any = await request.get("/api/system/monitor/", {
        showError: false,
        timeout: 15000,
      });
      const data = response?.data || {};
      const disks = Array.isArray(data.disks) ? data.disks : [];
      const diskUsage =
        disks.length > 0
          ? Math.round(
              disks.reduce((sum: number, disk: any) => {
                return sum + (Number(disk.percent) || 0);
              }, 0) / disks.length,
            )
          : 0;
      const status: SystemStatus = {
        cpuUsage: Math.round(Number(data.cpu?.cpu_percent) || 0),
        memoryUsage: Math.round(Number(data.memory?.percent) || 0),
        diskUsage,
        networkStatus: "normal",
      };
      if (
        status.cpuUsage >= 90 ||
        status.memoryUsage >= 90 ||
        status.diskUsage >= 95
      ) {
        status.networkStatus = "error";
      } else if (
        status.cpuUsage >= 75 ||
        status.memoryUsage >= 80 ||
        status.diskUsage >= 85
      ) {
        status.networkStatus = "warning";
      }
      return {
        success: true,
        code: 200,
        message: "success",
        data: status,
      };
    } catch (error) {
      console.error("获取系统状态失败:", error);
      return {
        success: false,
        code: 500,
        message: "获取系统状态失败",
        data: {
          cpuUsage: 0,
          memoryUsage: 0,
          diskUsage: 0,
          networkStatus: "error",
        },
      };
    }
  },

  // 获取访问趋势
  getVisitTrends: async (
    period: "week" | "month" | "year" = "week",
  ): Promise<ApiResponse<VisitTrend[]>> => {
    try {
      const trends = await dashboardApi.getMockVisitTrends(period);
      return {
        success: true,
        code: 200,
        message: "success",
        data: trends,
      };
    } catch (error) {
      console.error("获取访问趋势失败:", error);
      return {
        success: false,
        code: 500,
        message: "获取访问趋势失败",
        data: [],
      };
    }
  },

  // 获取完整仪表盘数据
  getDashboardData: async (): Promise<ApiResponse<DashboardData>> => {
    try {
      const [statsResp, activitiesResp, systemResp, trendsResp] =
        await Promise.all([
          dashboardApi.getRealStats(),
          dashboardApi.getRecentActivities(10),
          dashboardApi.getSystemStatus(),
          dashboardApi.getVisitTrends("week"),
        ]);

      return {
        success: true,
        code: 200,
        message: "success",
        data: {
          stats: statsResp.data,
          recentActivities: activitiesResp.data,
          systemStatus: systemResp.data,
          visitTrends: trendsResp.data,
        },
      };
    } catch (error) {
      console.error("获取完整仪表盘数据失败:", error);
      return {
        success: false,
        code: 500,
        message: "获取仪表盘数据失败",
        data: {
          stats: {
            totalUsers: 0,
            totalNotifications: 0,
            totalLogs: 0,
            totalKnowledge: 0,
            userGrowthRate: 0,
            notificationGrowthRate: 0,
            logGrowthRate: 0,
            knowledgeGrowthRate: 0,
          },
          recentActivities: [],
          systemStatus: {
            cpuUsage: 0,
            memoryUsage: 0,
            diskUsage: 0,
            networkStatus: "error",
          },
          visitTrends: [],
        },
      };
    }
  },

  // 模拟数据方法（用于开发阶段）
  getMockStats: (): Promise<DashboardStats> => {
    return new Promise((resolve) => {
      setTimeout(() => {
        resolve({
          totalUsers: 1128,
          totalNotifications: 893,
          totalLogs: 234,
          totalKnowledge: 560,
          userGrowthRate: 12,
          notificationGrowthRate: 8,
          logGrowthRate: -3,
          knowledgeGrowthRate: 15,
        });
      }, 500);
    });
  },

  getMockActivities: (): Promise<RecentActivity[]> => {
    return new Promise((resolve) => {
      setTimeout(() => {
        resolve([
          {
            id: 1,
            action: "用户 张三 登录了系统",
            time: "2分钟前",
            user: "张三",
            type: "login",
          },
          {
            id: 2,
            action: "管理员 李四 创建了新部门",
            time: "5分钟前",
            user: "李四",
            type: "create",
          },
          {
            id: 3,
            action: "用户 王五 修改了个人信息",
            time: "10分钟前",
            user: "王五",
            type: "update",
          },
          {
            id: 4,
            action: "系统自动备份完成",
            time: "1小时前",
            user: "系统",
            type: "system",
          },
          {
            id: 5,
            action: "新用户 赵六 注册成功",
            time: "2小时前",
            user: "赵六",
            type: "register",
          },
        ]);
      }, 300);
    });
  },

  getMockSystemStatus: (): Promise<SystemStatus> => {
    return new Promise((resolve) => {
      setTimeout(() => {
        resolve({
          cpuUsage: 45,
          memoryUsage: 67,
          diskUsage: 32,
          networkStatus: "normal",
        });
      }, 200);
    });
  },

  getMockVisitTrends: (
    period: "week" | "month" | "year" = "week",
  ): Promise<VisitTrend[]> => {
    return new Promise((resolve) => {
      setTimeout(() => {
        const data = {
          week: [
            { date: "周一", visits: 120, users: 80 },
            { date: "周二", visits: 150, users: 95 },
            { date: "周三", visits: 180, users: 110 },
            { date: "周四", visits: 200, users: 130 },
            { date: "周五", visits: 250, users: 160 },
            { date: "周六", visits: 180, users: 120 },
            { date: "周日", visits: 160, users: 100 },
          ],
          month: [
            { date: "第1周", visits: 800, users: 500 },
            { date: "第2周", visits: 950, users: 600 },
            { date: "第3周", visits: 1100, users: 700 },
            { date: "第4周", visits: 1200, users: 750 },
          ],
          year: [
            { date: "1月", visits: 3200, users: 2000 },
            { date: "2月", visits: 3800, users: 2400 },
            { date: "3月", visits: 4200, users: 2600 },
            { date: "4月", visits: 3900, users: 2300 },
            { date: "5月", visits: 4500, users: 2800 },
            { date: "6月", visits: 5000, users: 3100 },
          ],
        };
        resolve(data[period]);
      }, 400);
    });
  },
};

// 辅助函数：格式化时间为相对时间
function formatTimeAgo(dateString: string): string {
  const now = new Date();
  const date = new Date(dateString);
  const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (diffInSeconds < 60) {
    return `${diffInSeconds}秒前`;
  } else if (diffInSeconds < 3600) {
    const minutes = Math.floor(diffInSeconds / 60);
    return `${minutes}分钟前`;
  } else if (diffInSeconds < 86400) {
    const hours = Math.floor(diffInSeconds / 3600);
    return `${hours}小时前`;
  } else {
    const days = Math.floor(diffInSeconds / 86400);
    return `${days}天前`;
  }
}

// 辅助函数：将日志操作类型映射为活动类型
function mapLogTypeToActivityType(
  operationType: string,
): RecentActivity["type"] {
  if (!operationType) return "system";

  const lowerType = operationType.toLowerCase();

  if (lowerType.includes("login") || lowerType.includes("登录")) {
    return "login";
  } else if (
    lowerType.includes("create") ||
    lowerType.includes("创建") ||
    lowerType.includes("add") ||
    lowerType.includes("新增")
  ) {
    return "create";
  } else if (
    lowerType.includes("update") ||
    lowerType.includes("修改") ||
    lowerType.includes("edit") ||
    lowerType.includes("更新")
  ) {
    return "update";
  } else if (lowerType.includes("register") || lowerType.includes("注册")) {
    return "register";
  } else if (
    lowerType.includes("view") ||
    lowerType.includes("查看") ||
    lowerType.includes("get") ||
    lowerType.includes("获取")
  ) {
    return "system";
  }
  return "system";
}
