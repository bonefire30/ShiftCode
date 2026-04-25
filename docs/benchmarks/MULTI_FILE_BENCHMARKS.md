# 多文件 Benchmark 第一阶段

这份文档定义了 ShiftCode 第一批多文件 Java-to-Go benchmark 项目类型。

第一阶段的目标不是覆盖所有真实世界 Java 项目形态，而是强制当前项目级工作流先解决第一批真正的多文件问题：

- 跨文件类型解析
- package 与模块边界
- 跨文件构造与接口装配
- 项目级 `go build` 正确性
- 依赖多个文件上下文的测试生成
- 当某一个坏文件拖垮整个项目时的 repair 行为

单文件 benchmark 已经证明基础 Java-to-Go 闭环可以工作。第一阶段接下来要隔离出的新瓶颈，应该是项目结构，而不是单个文件的语法翻译。

## 设计规则

每一个第一阶段多文件 benchmark 项目都应遵守以下规则。

1. 项目规模要足够小，方便调试。
2. 每个项目使用 3 到 8 个 Java 文件。
3. 每个项目只讲一个完整业务故事，不要拼接互不相关的文件。
4. 至少包含一条跨文件依赖链。
5. 必须通过项目级 `go build` 与 `go test` 来证明正确性。
6. 第一阶段避免框架过重的设定。不引入 Spring、Hibernate、Servlet 容器。
7. 优先选择纯 Java 项目，让难点集中在结构与语义，而不是框架配置。
8. 每个项目都应有一份收敛、明确、带显式契约的 `migration_prompt.txt`，保持和单文件 benchmark 一样的风格。

## 第一阶段项目类型

第一批建议包含 6 类项目。

## 1. 分层 CRUD 服务

### 结构

- `model/User.java`
- `repository/UserRepository.java`
- `repository/InMemoryUserRepository.java`
- `service/UserService.java`
- `service/UserValidator.java`
- `app/UserFacade.java`

### 主要测试点

- 跨文件 DTO 或实体 struct 映射
- 接口与实现分离，且位于不同文件
- 跨层构造注入
- 校验逻辑与 repository 委托
- package 命名一致性

### 为什么重要

这是最小但真实的后端项目形态。如果系统连 repository-service-model 这种拆分都不能稳定迁移，就还谈不上真实项目迁移。

### 必测检查项

- service 在写 repository 前先调用 validator
- service 依赖 repository 接口，而不是直接绑死具体实现
- 数据在 model、repository、service 多文件之间流转正确
- 生成测试覆盖 happy path 和校验失败路径

## 2. 策略模式支付流程

### 结构

- `payment/PaymentMethod.java`
- `payment/CreditCardPayment.java`
- `payment/PaypalPayment.java`
- `payment/PaymentFactory.java`
- `payment/PaymentService.java`
- `payment/PaymentLogger.java`

### 主要测试点

- 接口加多实现，且实现分散在不同文件
- 工厂选择逻辑
- service 基于接口类型进行编排
- 跨文件多态保持正确

### 为什么重要

这是单文件 polymorphism case 的自然多文件扩展。它检验系统能否在实现分散到多个文件时，仍然保持接口语义不漂移。

### 必测检查项

- factory 返回正确的具体策略实现
- service 通过接口进行委托调用
- logger 在预期路径上被调用
- 测试验证的是 dispatch 行为，而不只是返回字符串

## 3. 聚合型领域模型

### 结构

- `order/Order.java`
- `order/OrderItem.java`
- `order/Money.java`
- `order/OrderStatus.java`
- `order/OrderCalculator.java`
- `order/OrderService.java`

### 主要测试点

- 跨文件领域 struct、枚举或常量
- 多类型之间的集合处理
- helper 与 service 分离
- 使用共享类型完成业务规则计算

### 为什么重要

很多 Java 代码库本质上都是对象图。这类项目用于验证迁移系统能否保住一个小型领域模型，而不是把所有语义粗暴压扁到单文件里，或者破坏 package 关系。

### 必测检查项

- 总价计算正确使用 `OrderItem` 和 `Money`
- 状态流转规则保留正确
- helper 行为和 service 行为不漂移
- 测试断言的是共享类型之间的交互，而不只是顶层输出

## 4. 工具类加解析流水线

### 结构

- `config/Config.java`
- `config/ConfigParser.java`
- `config/ConfigSource.java`
- `util/StringUtil.java`
- `util/ValidationUtil.java`
- `app/ConfigLoader.java`

### 主要测试点

- parser 代码依赖多个 util 文件
- 字符串解析与校验逻辑分散在不同文件
- dependency fan-in，也就是一个文件同时依赖多个 helper
- util 包与 domain 包之间的跨包导入

### 为什么重要

这是很常见的“小项目 + 一堆 helper”形态。这类项目最容易在迁移时因为文件引用、package import 或 helper 命名漂移而出错。

### 必测检查项

- parser 正确调用 helper 函数
- 非法配置能够按显式契约被拒绝
- config loader 正确组合 source、parser 和 validation
- 测试验证跨文件组合行为，而不是只单测某个 helper

## 5. 事件总线 / 观察者迷你项目

### 结构

- `event/Event.java`
- `event/EventListener.java`
- `event/EventBus.java`
- `event/UserCreatedEvent.java`
- `listener/AuditListener.java`
- `listener/MetricsListener.java`
- `app/UserRegistrationService.java`

### 主要测试点

- 基于接口的回调，且分布在不同文件
- listener 集合管理
- side effect 扇出
- 调度与分发语义

### 为什么重要

这是第一类“行为比数据形状更重要”的项目。它用来验证：系统生成的测试是否能正确校验跨文件事件分发契约。

### 必测检查项

- 发布一个事件后，所有 listener 都收到通知
- registration service 发布了正确的事件类型
- listener side effect 能在测试中被观察到
- 测试验证的是 dispatch 契约，而不是最终汇总状态

## 6. 带错误映射的可重试客户端

### 结构

- `client/HttpClient.java`
- `client/ApiResponse.java`
- `client/RetryPolicy.java`
- `client/ApiException.java`
- `service/RemoteUserService.java`
- `service/ErrorMapper.java`

### 主要测试点

- 跨文件错误类型与响应类型
- retry policy 装配到 service 逻辑中
- 接口加 fake client 测试模式
- 错误分类逻辑跨多个文件传播

### 为什么重要

单文件异常处理远远不够。真实项目里，client、response、retry、error mapping 往往天然分散在不同文件里。这个项目用来验证系统能否保留这种结构，而不是把它们错误地揉平。

### 必测检查项

- 只在可重试条件下发生 retry
- service 对远端错误的映射一致
- 成功路径返回正确解析后的领域数据
- 测试通过 fake 或 spy 覆盖跨文件边界

## 覆盖矩阵

第一阶段至少要覆盖下面这些维度各一次。

| 维度 | 对应项目 |
|---|---|
| 接口与实现分离 | 1, 2, 5, 6 |
| 跨包导入 | 1, 4, 5, 6 |
| 多文件领域模型 | 1, 3 |
| 工厂或构造装配 | 1, 2 |
| helper fan-in | 4 |
| callback / observer 行为 | 5 |
| retry / error mapping | 6 |
| 项目级测试生成 | 全部 |
| 项目级失败后的 repair | 全部 |

## 第一阶段验收预期

一组好的第一阶段 benchmark，应满足以下标准。

1. 人类读者应能在 5 分钟内理解每个项目。
2. 每个项目都应有一份小而明确的迁移 prompt。
3. 每个项目至少包含一个“不能只看单文件就验证”的行为契约。
4. 如果跨文件推理出错，项目应以明显方式失败。
5. 测试聚焦项目契约，而不只是单文件能否编译。

## 第一阶段暂时不要纳入的内容

第一批多文件 benchmark 暂时不要引入以下类型。

- Spring Boot 依赖注入
- JPA 或 Hibernate 注解
- Servlet filter 或完整 Web Server
- 大量依赖反射的代码
- 多文件共享可变状态下的复杂线程模型
- Maven 多模块构建
- 外部服务或真实网络 I/O

这些都可以作为后续 benchmark，但它们会把框架和基础设施复杂度过早混进第一轮多文件验证中。

## 推荐建设顺序

第一阶段建议按以下顺序实现。

1. 分层 CRUD 服务
2. 策略模式支付流程
3. 聚合型领域模型
4. 工具类加解析流水线
5. 带错误映射的可重试客户端
6. 事件总线 / 观察者迷你项目

这个顺序会先覆盖最常见的结构性问题，再逐步进入更偏行为协同的多文件问题。

## 建议目录约定

建议为项目级 benchmark 使用新的数据集根目录。

```text
benchmark_projects/
  wave1/
    01_layered_crud_service/
    02_strategy_payment_flow/
    03_aggregate_domain_model/
    04_parser_pipeline/
    05_retryable_client/
    06_event_bus/
```

每个项目目录建议包含：

- 多文件 Java 源码树
- `migration_prompt.txt`
- 如有需要，可加入 expected behavior notes 或 test oracle 输入

第一阶段里，golden output 的格式可以保持灵活。真正的硬要求是：生成出来的 Go 项目必须能够成功 `go build` 和 `go test`。

## 总结

第一阶段要证明的核心只有一件事：ShiftCode 已经能迁移一个“小但真实”的项目形态，而且正确性依赖的是文件之间的关系，而不是只靠单文件翻译。

如果这 6 类项目都能稳定跑通，那么系统就具备进入第二阶段的条件。那时才适合把框架模式和更重的基础设施复杂度加入 benchmark 集合。
